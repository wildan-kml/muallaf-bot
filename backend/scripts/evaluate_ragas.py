"""Template evaluasi RAGAS untuk Muallaf Bot IMC-MASK.

Alur:
1. Baca daftar pertanyaan evaluasi dari CSV/XLSX.
2. Kirim pertanyaan ke endpoint FastAPI /api/chat.
3. Simpan raw response agar bisa diaudit.
4. Jalankan RAGAS untuk sampel yang bukan fallback dan memiliki konteks.

Contoh menjalankan:
    python backend/scripts/evaluate_ragas.py \
        --input docs/ragas_evaluation_questions_template.csv \
        --api-url http://127.0.0.1:8000/api/chat \
        --output docs/ragas_results.csv

    python backend/scripts/evaluate_ragas.py \
        --input docs/ragas_evaluation_input.xlsx \
        --sheet "Evaluasi RAGAS" \
        --api-url http://127.0.0.1:8000/api/chat \
        --output docs/ragas_results.csv

- Untuk metrik berbasis LLM, RAGAS membutuhkan evaluator LLM. Proyek ini
  mendukung evaluator Gemini lewat RAGAS_LLM_PROVIDER=gemini dan evaluator
  lokal Ollama lewat RAGAS_LLM_PROVIDER=ollama.
- Jika kuota evaluator LLM habis, RAGAS dapat mengembalikan skor kosong/NaN.
  Gunakan kolom ragas_status dan ragas_note pada output CSV untuk melihatnya.
- Secara default, embedding evaluator memakai model lokal agar tidak ikut
  menghabiskan kuota API Gemini.
- Kolom reference_answer sebaiknya diisi untuk metrik yang membutuhkan jawaban
  pembanding. Kolom reference_contexts dapat diisi dengan potongan konteks
  ideal, dipisahkan oleh " ||| ".
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import posixpath
import re
import sys
import types
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib import error, request
from zipfile import ZipFile


DEFAULT_INPUT = Path("docs/ragas_evaluation_questions_template.csv")
DEFAULT_OUTPUT = Path("docs/ragas_results.csv")
DEFAULT_RAW_OUTPUT = Path("docs/ragas_raw_responses.jsonl")
DEFAULT_API_URL = "http://127.0.0.1:8000/api/chat"
DEFAULT_XLSX_SHEET = "Evaluasi RAGAS"
DEFAULT_CHUNKS_PATH = Path("backend/data/processed/chunks.json")
DEFAULT_MAX_CONTEXT_CHARS = 1800


HEADER_ALIASES = {
    "id": ["id", "no", "nomor"],
    "question": ["question", "pertanyaan"],
    "reference_answer": ["reference_answer", "jawaban acuan", "ground truth", "jawaban referensi"],
    "reference_contexts": ["reference_contexts", "konteks hasil retrieval", "konteks acuan"],
    "expected_source": ["expected_source", "target sumber rujukan", "target sumber/konteks"],
    "category": ["category", "kategori"],
    "should_fallback": ["should_fallback", "fallback", "perlu fallback"],
}


def normalize_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def canonicalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {normalize_header(key): str(value or "").strip() for key, value in row.items()}
    canonical: dict[str, str] = {}

    for target, aliases in HEADER_ALIASES.items():
        canonical[target] = ""
        for alias in aliases:
            if alias in normalized:
                canonical[target] = normalized[alias]
                break

    # Keep any extra columns for debugging/future use.
    for key, value in normalized.items():
        canonical.setdefault(key, value)

    return canonical


def read_csv_questions(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [canonicalize_row(row) for row in csv.DictReader(file)]


def read_xlsx_rows(path: Path, sheet_name: str) -> list[dict[str, str]]:
    """Read a worksheet without requiring pandas/openpyxl.

    This is intentionally small and only supports plain cell values, which is
    enough for the evaluation workbook.
    """
    ns = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    with ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", ns):
                shared_strings.append("".join((text.text or "") for text in item.findall(".//a:t", ns)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in relationships}

        sheet_path = ""
        available_sheets: list[str] = []
        for sheet in workbook.findall("a:sheets/a:sheet", ns):
            name = sheet.attrib["name"]
            available_sheets.append(name)
            if name != sheet_name:
                continue
            rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            target = relationship_map[rel_id]
            sheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))

        if not sheet_path:
            raise ValueError(f"Sheet '{sheet_name}' tidak ditemukan. Sheet tersedia: {', '.join(available_sheets)}")

        def column_number(cell_ref: str) -> int:
            letters = re.match(r"([A-Z]+)", cell_ref)
            if not letters:
                return 0
            value = 0
            for char in letters.group(1):
                value = value * 26 + ord(char) - 64
            return value

        def cell_value(cell: ET.Element) -> str:
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                return "".join(text.text or "" for text in cell.findall(".//a:t", ns))

            value = cell.find("a:v", ns)
            if value is None:
                return ""

            raw = value.text or ""
            if cell_type == "s" and raw.isdigit() and int(raw) < len(shared_strings):
                return shared_strings[int(raw)]
            return raw

        sheet_root = ET.fromstring(archive.read(sheet_path))
        raw_rows: list[list[str]] = []
        for row in sheet_root.findall("a:sheetData/a:row", ns):
            values = {
                column_number(cell.attrib["r"]): cell_value(cell)
                for cell in row.findall("a:c", ns)
                if cell.attrib.get("r")
            }
            if values:
                raw_rows.append([values.get(index, "") for index in range(1, max(values) + 1)])

    if not raw_rows:
        return []

    headers = [str(item or "").strip() for item in raw_rows[0]]
    rows: list[dict[str, str]] = []
    for raw_row in raw_rows[1:]:
        if not any(str(item).strip() for item in raw_row):
            continue
        row = {
            headers[index]: str(raw_row[index] if index < len(raw_row) else "").strip()
            for index in range(len(headers))
            if headers[index]
        }
        rows.append(canonicalize_row(row))
    return rows


def read_questions(path: Path, sheet_name: str) -> list[dict[str, str]]:
    if path.suffix.lower() == ".xlsx":
        return read_xlsx_rows(path, sheet_name=sheet_name)
    return read_csv_questions(path)


def load_backend_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def post_chat(api_url: str, question: str, timeout: int = 120) -> dict[str, Any]:
    payload = json.dumps({"question": question}).encode("utf-8")
    req = request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(
            "Tidak bisa menghubungi endpoint chatbot. Pastikan FastAPI sudah berjalan "
            f"dan api-url benar: {api_url}"
        ) from exc


def split_contexts(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|||") if item.strip()]


def load_chunk_lookup(chunks_path: Path) -> dict[str, dict[str, Any]]:
    """Load processed chunk content so RAGAS receives real contexts.

    The public chat API intentionally returns compact source metadata. RAGAS,
    however, must evaluate against the actual retrieved text, not just
    "book title, page" labels. This lookup maps API source chunk_id values back
    to the processed chunk content saved by build_knowledge_base.py.
    """
    if not chunks_path.exists():
        return {}

    with chunks_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, dict):
        chunks = payload.get("chunks") or payload.get("documents") or []
    else:
        chunks = payload

    lookup: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
        content = str(chunk.get("content") or chunk.get("text") or "").strip()
        if chunk_id and content:
            lookup[chunk_id] = chunk
    return lookup


def source_label(source: dict[str, Any]) -> str:
    title = str(source.get("document_title") or "").strip()
    page = source.get("page_number")
    label = str(source.get("reference_label") or "").strip()

    pieces = [title]
    if page:
        pieces.append(f"halaman {page}")
    if label:
        pieces.append(label)
    return ", ".join(piece for piece in pieces if piece)


def trim_context(text: str, max_chars: int) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def context_from_source(
    source: dict[str, Any],
    chunk_lookup: dict[str, dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> str:
    chunk_id = str(source.get("chunk_id") or "").strip()
    if chunk_id and chunk_lookup and chunk_id in chunk_lookup:
        chunk = chunk_lookup[chunk_id]
        content = str(chunk.get("content") or chunk.get("text") or "").strip()
        if content:
            title = str(chunk.get("document_title") or source.get("document_title") or "").strip()
            page = chunk.get("page_number") or source.get("page_number")
            prefix = f"[{chunk_id} | {title} | halaman {page}]\n" if title and page else ""
            return trim_context(prefix + content, max_context_chars)

    preview = str(source.get("content_preview") or "").strip()
    if preview:
        return trim_context(preview, max_context_chars)

    return source_label(source)


def contexts_from_sources(
    sources: list[dict[str, Any]],
    chunk_lookup: dict[str, dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> list[str]:
    contexts: list[str] = []
    for source in sources or []:
        context = context_from_source(
            source=source,
            chunk_lookup=chunk_lookup,
            max_context_chars=max_context_chars,
        )
        if context:
            contexts.append(context)
    return contexts


def labels_from_sources(sources: list[dict[str, Any]]) -> list[str]:
    return [label for source in sources or [] if (label := source_label(source))]


def collect_responses(
    rows: list[dict[str, str]],
    api_url: str,
    raw_output: Path,
    chunk_lookup: dict[str, dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    delay_seconds: float = 0.0,
    api_timeout: int = 120,
) -> list[dict[str, Any]]:
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []

    with raw_output.open("w", encoding="utf-8") as file:
        for index, row in enumerate(rows, start=1):
            question = row["question"].strip()
            if not question:
                continue
            print(f"[{index}/{len(rows)}] Evaluating: {question}")
            response = post_chat(api_url, question, timeout=api_timeout)
            sources = response.get("sources") or []
            retrieved_contexts = contexts_from_sources(
                sources,
                chunk_lookup=chunk_lookup,
                max_context_chars=max_context_chars,
            )
            retrieved_context_labels = labels_from_sources(sources)
            reference_contexts = split_contexts(row.get("reference_contexts"))

            sample = {
                "id": row.get("id") or f"Q{index:03d}",
                "user_input": question,
                "response": response.get("answer") or response.get("reply") or "",
                "retrieved_contexts": retrieved_contexts,
                "retrieved_context_labels": retrieved_context_labels,
                "reference": row.get("reference_answer", "").strip() or None,
                "reference_contexts": reference_contexts or None,
                "expected_source": row.get("expected_source", "").strip(),
                "category": row.get("category", "").strip(),
                "should_fallback": str(row.get("should_fallback", "")).lower() == "true",
                "mode": response.get("mode"),
                "escalation": response.get("escalation"),
                "retrieval_confidence": response.get("retrieval_confidence"),
                "source_count": len(sources),
                "raw_sources": sources,
            }
            samples.append(sample)
            file.write(json.dumps(sample, ensure_ascii=False) + "\n")

            if delay_seconds:
                time.sleep(delay_seconds)

    return samples


def read_raw_samples(
    raw_output: Path,
    chunk_lookup: dict[str, dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> list[dict[str, Any]]:
    """Reuse saved API responses and enrich old files with full chunk contexts."""
    samples: list[dict[str, Any]] = []
    with raw_output.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            sources = sample.get("raw_sources") or []
            if sources:
                sample["retrieved_contexts"] = contexts_from_sources(
                    sources,
                    chunk_lookup=chunk_lookup,
                    max_context_chars=max_context_chars,
                )
                sample["retrieved_context_labels"] = labels_from_sources(sources)
            else:
                sample.setdefault("retrieved_context_labels", [])
            samples.append(sample)
    return samples


def build_ragas_metrics(has_references: bool, metric_names: set[str] | None = None) -> list[Any]:
    """Load metrics with compatibility for newer and older RAGAS versions."""
    patch_ragas_vertexai_import()
    try:
        from ragas.metrics import (
            Faithfulness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
            ResponseRelevancy,
        )

        selected = metric_names or {"faithfulness", "response_relevancy", "context_precision", "context_recall"}
        metrics: list[Any] = []
        if "faithfulness" in selected:
            metrics.append(Faithfulness())
        if "response_relevancy" in selected:
            metrics.append(ResponseRelevancy())
        if has_references and "context_precision" in selected:
            metrics.append(LLMContextPrecisionWithReference())
        if has_references and "context_recall" in selected:
            metrics.append(LLMContextRecall())
        return metrics
    except Exception:
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

        selected = metric_names or {"faithfulness", "response_relevancy", "context_precision", "context_recall"}
        metrics = []
        if "faithfulness" in selected:
            metrics.append(faithfulness)
        if "response_relevancy" in selected:
            metrics.append(answer_relevancy)
        if has_references and "context_precision" in selected:
            metrics.append(context_precision)
        if has_references and "context_recall" in selected:
            metrics.append(context_recall)
        return metrics


def build_ragas_llm() -> Any | None:
    """Opsional: pakai Gemini atau Ollama sebagai evaluator RAGAS.

    Default None berarti RAGAS memakai konfigurasi default lingkungannya.
    Untuk Gemini:
      pip install langchain-google-genai
      set RAGAS_LLM_PROVIDER=gemini
      set GEMINI_API_KEY=...

    Untuk Ollama lokal:
      pip install langchain-ollama
      set RAGAS_LLM_PROVIDER=ollama
      set RAGAS_OLLAMA_MODEL=llama3.2:3b
    """
    provider = os.getenv("RAGAS_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "")).lower()

    if provider == "ollama":
        patch_ragas_vertexai_import()
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            try:
                from langchain_community.chat_models import ChatOllama
            except ImportError as exc:
                raise RuntimeError(
                    "Evaluator Ollama membutuhkan paket langchain-ollama "
                    "atau adapter ChatOllama dari langchain-community."
                ) from exc

        from ragas.llms import LangchainLLMWrapper

        model_name = os.getenv("RAGAS_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        num_predict = int(os.getenv("RAGAS_OLLAMA_NUM_PREDICT", "256"))
        response_format = os.getenv("RAGAS_OLLAMA_FORMAT", "json").strip() or None
        ensure_ollama_ready(base_url=base_url, model_name=model_name)
        llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            num_predict=num_predict,
            format=response_format,
        )
        return LangchainLLMWrapper(llm)

    if provider == "gemini":
        # Jangan otomatis memakai GEMINI_MODEL chatbot untuk evaluasi. RAGAS
        # memanggil evaluator berkali-kali per baris, sehingga model chatbot
        # seperti gemini-2.5-flash cepat terkena limit free tier. Gunakan model
        # evaluasi ringan kecuali dioverride lewat RAGAS_GEMINI_MODEL.
        model_name = os.getenv("RAGAS_GEMINI_MODEL", "gemini-2.0-flash-lite")

        patch_ragas_vertexai_import()
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from ragas.llms import LangchainLLMWrapper
        except ImportError as exc:
            raise RuntimeError("Gemini evaluator membutuhkan paket langchain-google-genai dan ragas.") from exc

        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY belum tersedia untuk evaluator RAGAS.")

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0,
        )
        return LangchainLLMWrapper(llm)

    return None


def ensure_ollama_ready(base_url: str, model_name: str) -> None:
    """Fail early with a useful message before RAGAS starts async scoring."""
    tags_url = f"{base_url.rstrip('/')}/api/tags"

    try:
        with request.urlopen(tags_url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(
            "Evaluator RAGAS disetel memakai Ollama, tetapi server Ollama tidak "
            f"bisa diakses di {base_url}. Jalankan Ollama terlebih dahulu "
            "(`ollama serve` atau buka aplikasi Ollama), lalu ulangi evaluasi."
        ) from exc

    models = payload.get("models", [])
    available = sorted(
        str(item.get("name", "")).strip()
        for item in models
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    )

    if model_name not in available:
        model_list = ", ".join(available) if available else "belum ada model"
        raise RuntimeError(
            f"Model Ollama '{model_name}' belum tersedia. Jalankan "
            f"`ollama pull {model_name}` terlebih dahulu. Model tersedia: {model_list}."
        )


def build_ragas_embeddings() -> Any | None:
    """Use the same local multilingual embedding model for RAGAS metrics.

    RAGAS defaults to OpenAI embeddings for metrics such as response relevancy.
    This project uses a local sentence-transformer model, so the evaluator should
    do the same to avoid requiring an OpenAI key.
    """
    patch_ragas_vertexai_import()
    provider = os.getenv("RAGAS_EMBEDDING_PROVIDER", "").lower()

    if provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from ragas.embeddings.base import LangchainEmbeddingsWrapper

        model_name = os.getenv("RAGAS_GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001")
        embeddings = GoogleGenerativeAIEmbeddings(model=model_name)
        return LangchainEmbeddingsWrapper(embeddings)

    model_name = os.getenv("RAGAS_EMBEDDING_MODEL", os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"))

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        from langchain_community.embeddings import HuggingFaceEmbeddings

    from ragas.embeddings.base import LangchainEmbeddingsWrapper

    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        encode_kwargs={"normalize_embeddings": True},
    )
    return LangchainEmbeddingsWrapper(embeddings)


def patch_ragas_vertexai_import() -> None:
    """RAGAS 0.4.x imports an old VertexAI adapter during package import.

    The project evaluates with Gemini, not VertexAI. Newer langchain-community
    versions no longer ship langchain_community.chat_models.vertexai, so a tiny
    stub keeps RAGAS importable without adding unused Google Vertex dependencies.
    """
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return

    module = types.ModuleType(module_name)

    class ChatVertexAI:  # pragma: no cover - compatibility shim only
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("ChatVertexAI tidak digunakan dalam evaluasi ini.")

    module.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = module


def run_ragas(
    samples: list[dict[str, Any]],
    metric_names: set[str] | None = None,
    raise_ragas_errors: bool = False,
    timeout_seconds: int = 600,
    max_workers: int = 1,
) -> Any:
    patch_ragas_vertexai_import()
    import inspect

    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.run_config import RunConfig

    ragas_rows = []
    for sample in samples:
        if sample["should_fallback"]:
            continue
        if not sample["retrieved_contexts"]:
            continue

        kwargs = {
            "user_input": sample["user_input"],
            "response": sample["response"],
            "retrieved_contexts": sample["retrieved_contexts"],
        }
        if sample.get("reference"):
            kwargs["reference"] = sample["reference"]
        if sample.get("reference_contexts"):
            kwargs["reference_contexts"] = sample["reference_contexts"]
        ragas_rows.append(SingleTurnSample(**kwargs))

    if not ragas_rows:
        raise RuntimeError("Tidak ada sampel valid untuk RAGAS. Isi pertanyaan dan pastikan konteks retrieval tersedia.")

    dataset = EvaluationDataset(samples=ragas_rows)
    has_references = any(sample.get("reference") for sample in samples)
    metrics = build_ragas_metrics(has_references=has_references, metric_names=metric_names)
    if not metrics:
        raise RuntimeError("Tidak ada metric RAGAS yang dipilih.")
    llm = build_ragas_llm()
    embeddings = build_ragas_embeddings()

    evaluate_kwargs = {
        "dataset": dataset,
        "metrics": metrics,
        "embeddings": embeddings,
        "run_config": RunConfig(timeout=timeout_seconds, max_workers=max_workers),
        "show_progress": True,
    }
    if llm is not None:
        evaluate_kwargs["llm"] = llm
    if "raise_exceptions" in inspect.signature(evaluate).parameters:
        evaluate_kwargs["raise_exceptions"] = raise_ragas_errors

    return evaluate(**evaluate_kwargs)


def is_missing_score(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return not text or text.lower() == "nan"


def clean_score_value(value: Any) -> str:
    if is_missing_score(value):
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def clean_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_for_json(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def pick_score(row: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        if alias in row:
            return row[alias]
    return None


RAGAS_SCORE_COLUMNS = {
    "faithfulness": ["faithfulness"],
    "response_relevancy": ["response_relevancy", "answer_relevancy"],
    "context_precision": ["context_precision", "llm_context_precision_with_reference"],
    "context_recall": ["context_recall"],
}


def format_ragas_scores(row: dict[str, Any] | None) -> dict[str, str]:
    scores: dict[str, str] = {}
    for column, aliases in RAGAS_SCORE_COLUMNS.items():
        scores[column] = clean_score_value(pick_score(row or {}, aliases))
    return scores


def ragas_status_for_sample(sample: dict[str, Any], score_row: dict[str, Any] | None, ragas_was_run: bool) -> tuple[str, str]:
    if sample["should_fallback"]:
        return "skipped_fallback", "Sampel ditandai fallback, tidak dievaluasi RAGAS."
    if not sample["retrieved_contexts"]:
        return "skipped_no_context", "Tidak ada retrieved_contexts untuk sampel ini."
    if not ragas_was_run:
        return "not_run", "RAGAS tidak dijalankan. Gunakan tanpa --skip-ragas untuk scoring."
    if score_row is None:
        return "missing_result", "Tidak ada baris skor RAGAS untuk sampel ini."

    scores = format_ragas_scores(score_row)
    if all(not value for value in scores.values()):
        return "failed_or_quota_limited", "Semua skor kosong/NaN. Cek quota/rate limit evaluator LLM atau error RAGAS."
    if any(not value for value in scores.values()):
        return "partial", "Sebagian metrik kosong. Cek kolom skor dan log evaluator."
    return "scored", ""


def write_results_csv(samples: list[dict[str, Any]], ragas_result: Any | None, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    ragas_rows: list[dict[str, Any]] = []

    if ragas_result is not None:
        ragas_df = ragas_result.to_pandas()
        ragas_rows = ragas_df.to_dict(orient="records")

    fieldnames = [
        "id",
        "question",
        "category",
        "should_fallback",
        "mode",
        "escalation",
        "retrieval_confidence",
        "source_count",
        "answer",
        "retrieved_context_count",
        "retrieved_context_labels",
        "retrieved_contexts",
        "expected_source",
        "faithfulness",
        "response_relevancy",
        "context_precision",
        "context_recall",
        "ragas_status",
        "ragas_note",
        "ragas_scores_json",
    ]

    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        ragas_index = 0
        ragas_was_run = ragas_result is not None
        for sample in samples:
            score_row = None
            if not sample["should_fallback"] and sample["retrieved_contexts"] and ragas_index < len(ragas_rows):
                score_row = ragas_rows[ragas_index]
                ragas_index += 1

            scores = format_ragas_scores(score_row)
            ragas_status, ragas_note = ragas_status_for_sample(
                sample=sample,
                score_row=score_row,
                ragas_was_run=ragas_was_run,
            )
            score_payload = ""
            if score_row is not None:
                score_payload = json.dumps(clean_for_json(score_row), ensure_ascii=False, allow_nan=False)

            writer.writerow(
                {
                    "id": sample["id"],
                    "question": sample["user_input"],
                    "category": sample["category"],
                    "should_fallback": sample["should_fallback"],
                    "mode": sample["mode"],
                    "escalation": sample["escalation"],
                    "retrieval_confidence": sample["retrieval_confidence"],
                    "source_count": sample["source_count"],
                    "answer": sample["response"],
                    "retrieved_context_count": len(sample["retrieved_contexts"] or []),
                    "retrieved_context_labels": " | ".join(sample.get("retrieved_context_labels") or []),
                    "retrieved_contexts": " | ".join(sample["retrieved_contexts"] or []),
                    "expected_source": sample["expected_source"],
                    "faithfulness": scores["faithfulness"],
                    "response_relevancy": scores["response_relevancy"],
                    "context_precision": scores["context_precision"],
                    "context_recall": scores["context_recall"],
                    "ragas_status": ragas_status,
                    "ragas_note": ragas_note,
                    "ragas_scores_json": score_payload,
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate IMC-MASK Muallaf Bot with RAGAS.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--sheet", default=DEFAULT_XLSX_SHEET, help="Nama sheet jika input berupa .xlsx.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument(
        "--chunks-path",
        type=Path,
        default=DEFAULT_CHUNKS_PATH,
        help="Path chunks.json untuk memperkaya retrieved_contexts RAGAS dengan isi chunk asli.",
    )
    parser.add_argument(
        "--max-context-chars",
        type=int,
        default=DEFAULT_MAX_CONTEXT_CHARS,
        help="Batas karakter per retrieved context yang dikirim ke RAGAS. Gunakan 0 untuk tanpa batas.",
    )
    parser.add_argument(
        "--reuse-raw",
        action="store_true",
        help="Gunakan raw-output JSONL yang sudah ada dan jangan panggil endpoint /api/chat lagi.",
    )
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument(
        "--api-timeout",
        type=int,
        default=300,
        help="Timeout request ke endpoint /api/chat dalam detik. Gunakan nilai besar saat backend memakai Ollama lokal.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Batasi jumlah baris untuk uji coba awal.")
    parser.add_argument(
        "--metrics",
        default="faithfulness,response_relevancy,context_precision,context_recall",
        help="Daftar metric: faithfulness,response_relevancy,context_precision,context_recall",
    )
    parser.add_argument("--skip-ragas", action="store_true", help="Hanya ambil respons API tanpa menjalankan RAGAS.")
    parser.add_argument(
        "--ragas-timeout",
        type=int,
        default=600,
        help="Timeout per tugas RAGAS dalam detik. Ollama lokal biasanya butuh nilai lebih besar dari default RAGAS.",
    )
    parser.add_argument(
        "--ragas-max-workers",
        type=int,
        default=1,
        help="Jumlah worker paralel RAGAS. Untuk Ollama lokal, gunakan 1 agar tidak timeout karena beban paralel.",
    )
    parser.add_argument(
        "--raise-ragas-errors",
        action="store_true",
        help="Naikkan error internal RAGAS agar penyebab skor kosong terlihat saat debugging.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_backend_env()
    chunk_lookup = load_chunk_lookup(args.chunks_path)
    if chunk_lookup:
        print(f"Loaded {len(chunk_lookup)} chunks from {args.chunks_path}")
    else:
        print(f"Warning: chunk lookup kosong. RAGAS akan memakai context dari API response saja: {args.chunks_path}")

    if args.reuse_raw:
        samples = read_raw_samples(
            raw_output=args.raw_output,
            chunk_lookup=chunk_lookup,
            max_context_chars=args.max_context_chars,
        )
        if args.limit > 0:
            samples = samples[: args.limit]
        print(f"Loaded {len(samples)} raw samples from {args.raw_output}")
    else:
        rows = read_questions(args.input, sheet_name=args.sheet)
        if args.limit > 0:
            rows = rows[: args.limit]
        print(f"Loaded {len(rows)} evaluation rows from {args.input}")
        samples = collect_responses(
            rows=rows,
            api_url=args.api_url,
            raw_output=args.raw_output,
            chunk_lookup=chunk_lookup,
            max_context_chars=args.max_context_chars,
            delay_seconds=args.delay_seconds,
            api_timeout=args.api_timeout,
        )

    ragas_result = None
    if not args.skip_ragas:
        metric_names = {name.strip() for name in args.metrics.split(",") if name.strip()}
        ragas_result = run_ragas(
            samples,
            metric_names=metric_names,
            raise_ragas_errors=args.raise_ragas_errors,
            timeout_seconds=args.ragas_timeout,
            max_workers=args.ragas_max_workers,
        )

    write_results_csv(samples=samples, ragas_result=ragas_result, output=args.output)
    print(f"Raw responses saved to: {args.raw_output}")
    print(f"Evaluation results saved to: {args.output}")


if __name__ == "__main__":
    main()
