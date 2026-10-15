from dataclasses import dataclass
import json
import logging
import math
import os
import re
from typing import Any

from langchain_core.embeddings import Embeddings

from .config import Settings
from .preprocessing import TextChunk


logger = logging.getLogger(__name__)


STOPWORDS = {
    "apa", "apakah", "bagaimana", "cara", "yang", "dan", "di", "ke", "dari",
    "itu", "ini", "saya", "aku", "untuk", "dengan", "harus", "boleh", "bisa",
    "mau", "ingin", "tentang", "seputar", "kalau", "jika", "orang", "mualaf",
    "muallaf", "islam", "adalah", "atau", "dalam", "pada", "sebagai",
}


CONVERSION_TERMS = {
    "masuk islam",
    "memeluk islam",
    "jadi muslim",
    "menjadi muslim",
    "pengislaman",
    "diislamkan",
    "masuk agama islam",
    "bersyahadat",
    "syahadat",
    "ikrar syahadat",
    "ikrar masuk islam",
}


@dataclass
class RetrievalResult:
    chunk: TextChunk
    score: float


_EMBEDDING_MODELS: dict[str, Any] = {}


class SentenceTransformerEmbeddings(Embeddings):
    """LangChain Embeddings adapter backed by the existing sentence-transformers model."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = _get_embedding_model(self.model_name)
        embeddings = model.encode(
            [f"passage: {text}" for text in texts],
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return _normalize_matrix(embeddings).tolist()

    def embed_query(self, text: str) -> list[float]:
        model = _get_embedding_model(self.model_name)
        embedding = model.encode(
            [f"query: {text}"],
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return _normalize_matrix(embedding)[0].tolist()


def _tokenize(text: str) -> set[str]:
    text = str(text or "").lower()
    text = re.sub(r"http\S+|www\.\S+", " ", text)
    text = re.sub(r"[^\w'\s-]", " ", text, flags=re.UNICODE)
    tokens = re.sub(r"\s+", " ", text).strip().split()
    return {token for token in tokens if len(token) > 2 and token not in STOPWORDS}


def _lexical_score(question: str, content: str) -> float:
    query_tokens = _tokenize(question)
    content_tokens = _tokenize(content)
    if not query_tokens or not content_tokens:
        return 0.0

    overlap = len(query_tokens & content_tokens)
    recall = overlap / max(len(query_tokens), 1)
    precision = overlap / max(len(content_tokens), 1)
    score = (0.82 * recall) + (0.18 * math.sqrt(precision))

    question_clean = " ".join(str(question).lower().split())
    content_clean = " ".join(str(content).lower().split())
    if question_clean and question_clean in content_clean:
        score += 0.25

    return min(score, 1.0)


def _looks_like_noise(content: str) -> bool:
    text = re.sub(r"\s+", " ", str(content or "").strip()).lower()
    if len(text) < 45:
        return True
    noisy_markers = {
        "daftar isi",
        "daftar kehadiran",
        "nama :",
        "tempat tgl lahir",
        "materi nama pembina",
        "paraf pembina",
        "paraf muallaf",
        "kata pengantar",
        "sambutan ketua",
    }
    if any(marker in text for marker in noisy_markers):
        return True
    return bool(re.search(r"\.{5,}|_{4,}|-{4,}", text))


def _expanded_question(question: str) -> str:
    cleaned = str(question or "").lower()
    additions: list[str] = []
    refers_imc_mask = (
        "imc" in cleaned
        or "imc-mask" in cleaned
        or "mask" in cleaned
        or "masjid agung sunda kelapa" in cleaned
        or "sunda kelapa" in cleaned
    )

    if (
        refers_imc_mask
        and (
            any(term in cleaned for term in CONVERSION_TERMS)
            or "alur" in cleaned
            or "prosedur" in cleaned
            or "proses" in cleaned
            or "layanan" in cleaned
            or "pelayanan" in cleaned
        )
    ):
        additions.append("alur ikrar syahadat imc-mask layanan pengislaman layanan masuk islam formulir dokumen persyaratan saksi pembinaan sertifikat")

    if any(term in cleaned for term in CONVERSION_TERMS):
        additions.append("syahadat dua kalimat syahadat ikrar syahadat tata cara masuk islam pengislaman masuk agama islam bersyahadat")
    if "alur ikrar" in cleaned or "proses ikrar" in cleaned or "syahadat di imc" in cleaned or "ikrar syahadat di imc" in cleaned:
        additions.append("alur ikrar syahadat imc-mask formulir dokumen persyaratan saksi pembinaan sertifikat")

    if (
        ("jadwal" in cleaned or "hari apa" in cleaned or "hari berapa" in cleaned or "jam berapa" in cleaned or "pukul berapa" in cleaned or "biasanya kapan" in cleaned)
        and ("pembinaan" in cleaned or "kelas" in cleaned or refers_imc_mask)
    ):
        additions.append("jadwal kelas pembinaan imc-mask rabu sabtu pukul 10.00 16.00 gedung fatahillah masjid agung sunda kelapa")

    if (
        "ayat" in cleaned
        or "al quran" in cleaned
        or "alquran" in cleaned
        or "al-quran" in cleaned
        or "quran" in cleaned
        or "surat" in cleaned
        or "surah" in cleaned
        or "qs" in cleaned
    ):
        additions.append("ayat al-qur'an surat surah qs artinya firman allah arab")

    if (
        "belajar al-qur" in cleaned
        or "belajar al qur" in cleaned
        or "belajar quran" in cleaned
        or "belajar qur'an" in cleaned
        or "mengaji" in cleaned
        or "ngaji" in cleaned
        or (
            ("al-qur" in cleaned or "al qur" in cleaned or "quran" in cleaned or "qur'an" in cleaned)
            and ("dari nol" in cleaned or "pemula" in cleaned or "mulai dari mana" in cleaned or "dasar" in cleaned)
        )
    ):
        additions.append("belajar al-qur'an dari nol huruf hijaiyah membaca al-qur'an tajwid dasar pengenalan al-qur'an mengaji pemula")

    if (
        "wudhu" in cleaned
        or "wudu" in cleaned
        or "berwudhu" in cleaned
        or "bersuci" in cleaned
        or "thaharah" in cleaned
    ):
        additions.append("wudhu wudu berwudhu bersuci thaharah membasuh rukun wudhu syarat wudhu hadats kecil sebelum shalat")

    if (
        "tayamum" in cleaned
        or "tayammum" in cleaned
        or "tidak ada air" in cleaned
        or "ga ada air" in cleaned
        or "nggak ada air" in cleaned
    ):
        additions.append("tayamum pengganti wudhu tidak ada air sakit debu tanah suci tata cara tayamum sebelum shalat")

    if "shalat" in cleaned or "sholat" in cleaned:
        additions.append("shalat sholat ayat al-qur'an tentang shalat artinya surat")

    if "tayamum" in cleaned or "mandi wajib" in cleaned or "mandi janabah" in cleaned:
        additions.append("tayamum mandi wajib mandi janabah hadats besar bersuci ibadah praktis")

    if "pembinaan" in cleaned or "materi" in cleaned or "setelah syahadat" in cleaned:
        additions.append("materi pembinaan mualaf studi islam dasar fiqih ibadah akhlaq karimah pengenalan al-quran")

    if "baru tertarik" in cleaned or "mengenal islam" in cleaned or "mulai dari mana" in cleaned:
        additions.append("dasar islam rukun iman rukun islam syahadat pembinaan mualaf akidah ibadah akhlak")

    if (
        "belajar ibadah" in cleaned
        or "mulai belajar ibadah" in cleaned
        or "ibadah dari mana" in cleaned
        or ("mualaf" in cleaned and "bingung" in cleaned)
    ):
        additions.append("mualaf belajar ibadah bertahap mulai dari bersuci wudhu shalat doa pendek akhlak pembinaan dasar fiqih ibadah")

    if "keluarga" in cleaned or "orang tua" in cleaned or "non-muslim" in cleaned or "non muslim" in cleaned:
        additions.append("akhlak keluarga orang tua berbuat baik hormat sabar non muslim")

    if "pendampingan" in cleaned or "pembina" in cleaned or "layanan imc-mask" in cleaned:
        additions.append("bimbingan pembinaan mualaf ikrar syahadat konsultasi agama pendampingan imc-mask")

    return " ".join([question, *additions]).strip()


def _priority_bonus(question: str, chunk: TextChunk) -> float:
    cleaned_question = str(question or "").lower()
    content = f"{chunk.document_title} {chunk.content}".lower()
    bonus = 0.0

    asks_conversion = any(term in cleaned_question for term in CONVERSION_TERMS)
    asks_imc_conversion_flow = (
        (
            "imc" in cleaned_question
            or "imc-mask" in cleaned_question
            or "mask" in cleaned_question
            or "masjid agung sunda kelapa" in cleaned_question
            or "sunda kelapa" in cleaned_question
        )
        and (
            any(term in cleaned_question for term in CONVERSION_TERMS)
            or "alur" in cleaned_question
            or "prosedur" in cleaned_question
            or "proses" in cleaned_question
            or "layanan" in cleaned_question
            or "pelayanan" in cleaned_question
        )
    )
    if asks_conversion:
        if "syahadat" in content:
            bonus += 0.12
        if "dua kalimat syahadat" in content or "mengucapkan kalimat syahadat" in content:
            bonus += 0.10
        if "ikrar" in content:
            bonus += 0.04
    if asks_imc_conversion_flow:
        if "alur ikrar syahadat di imc-mask" in content:
            bonus += 0.28
        if "website international muallaf center" in content:
            bonus += 0.18
        if "formulir" in content and "saksi" in content and "sertifikat" in content:
            bonus += 0.16
    if (
        "alur ikrar" in cleaned_question
        or "proses ikrar" in cleaned_question
        or "syahadat di imc" in cleaned_question
        or "ikrar syahadat di imc" in cleaned_question
    ):
        if "alur ikrar syahadat" in content:
            bonus += 0.14
        if "formulir" in content and "saksi" in content and "sertifikat" in content:
            bonus += 0.12
        if "imc-mask" in content or "website international muallaf center" in content:
            bonus += 0.12

    if (
        ("jadwal" in cleaned_question or "hari apa" in cleaned_question or "hari berapa" in cleaned_question or "jam berapa" in cleaned_question or "pukul berapa" in cleaned_question or "biasanya kapan" in cleaned_question)
        and ("pembinaan" in cleaned_question or "kelas" in cleaned_question or "imc" in cleaned_question or "imc-mask" in cleaned_question or "mask" in cleaned_question)
    ):
        if "website international muallaf center" in content:
            bonus += 0.18
        if "jadwal kelas setiap hari rabu dan sabtu" in content:
            bonus += 0.24
        if "pukul 10.00 sampai 16.00 wib" in content:
            bonus += 0.16

    if (
        (
            "wudhu" in cleaned_question
            or "wudu" in cleaned_question
            or "berwudhu" in cleaned_question
            or "bersuci" in cleaned_question
            or "thaharah" in cleaned_question
        )
        and (
            "wudhu" in content
            or "wudu" in content
            or "bersuci" in content
            or "thaharah" in content
        )
    ):
        bonus += 0.10
        if "tata cara ibadah praktis untuk mualaf baznas" in content:
            bonus += 0.08

    if (
        ("tayamum" in cleaned_question or "mandi wajib" in cleaned_question or "mandi janabah" in cleaned_question)
        and ("tayamum" in content or "mandi wajib" in content or "janabah" in content)
    ):
        bonus += 0.12
        if "tata cara ibadah praktis untuk mualaf baznas" in content:
            bonus += 0.08

    if (
        (
            "tidak ada air" in cleaned_question
            or "ga ada air" in cleaned_question
            or "nggak ada air" in cleaned_question
            or "tayamum" in cleaned_question
            or "tayammum" in cleaned_question
        )
        and ("tayamum" in content or "tidak menjumpai air" in content or "debu" in content)
    ):
        bonus += 0.18
        if "tata cara ibadah praktis untuk mualaf baznas" in content:
            bonus += 0.10

    if (
        ("shalat" in cleaned_question or "sholat" in cleaned_question)
        and ("shalat" in content or "sholat" in content)
        and "tata cara ibadah praktis untuk mualaf baznas" in content
    ):
        bonus += 0.08

    if (
        ("ayat" in cleaned_question or "quran" in cleaned_question or "al quran" in cleaned_question or "alquran" in cleaned_question or "al-quran" in cleaned_question)
        and ("artinya:" in content or "qs." in content or "surat" in content or "ayat" in content)
    ):
        bonus += 0.18
    if (
        (
            "belajar al-qur" in cleaned_question
            or "belajar al qur" in cleaned_question
            or "belajar quran" in cleaned_question
            or "mengaji" in cleaned_question
            or "ngaji" in cleaned_question
            or (
                ("al-qur" in cleaned_question or "al qur" in cleaned_question or "quran" in cleaned_question or "qur'an" in cleaned_question)
                and ("dari nol" in cleaned_question or "pemula" in cleaned_question or "mulai dari mana" in cleaned_question)
            )
        )
        and (
            "pengenalan al-qur" in content
            or "huruf hijaiyah" in content
            or "membaca al-qur" in content
            or "tajwid" in content
        )
    ):
        bonus += 0.16
    if (
        ("shalat" in cleaned_question or "sholat" in cleaned_question)
        and ("shalat" in content or "sholat" in content)
        and ("artinya:" in content or "surat" in content or "ayat" in content)
    ):
        bonus += 0.12

    if ("pembinaan" in cleaned_question or "materi" in cleaned_question) and "materi" in content:
        bonus += 0.05

    if (
        (
            "belajar ibadah" in cleaned_question
            or "mulai belajar ibadah" in cleaned_question
            or "ibadah dari mana" in cleaned_question
            or ("mualaf" in cleaned_question and "bingung" in cleaned_question)
        )
        and (
            "studi islam dasar" in content
            or "fiqih ibadah" in content
            or "akhlaq karimah" in content
            or "pengenalan al-qur" in content
            or "wudhu" in content
            or "shalat" in content
        )
    ):
        bonus += 0.14

    if (
        ("baru tertarik" in cleaned_question or "mengenal islam" in cleaned_question or "mulai dari mana" in cleaned_question)
        and ("rukun islam" in content or "rukun iman" in content or "syahadat" in content)
    ):
        bonus += 0.08

    if (
        ("keluarga" in cleaned_question or "orang tua" in cleaned_question)
        and ("orang tua" in content or "akhlak" in content or "keluarga" in content)
    ):
        bonus += 0.08

    if (
        ("pendampingan" in cleaned_question or "pembina" in cleaned_question)
        and ("pembinaan" in content or "bimbingan" in content or "muallaf center" in content)
    ):
        bonus += 0.08

    if _looks_like_noise(chunk.content):
        bonus -= 0.22

    return bonus


def save_chunks(chunks: list[TextChunk], path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [chunk.to_dict() for chunk in chunks]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_chunks(path) -> list[TextChunk]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    return [TextChunk.from_dict(item) for item in raw]


def _active_pdf_file_names(settings: Settings) -> set[str]:
    raw_dir = settings.raw_pdfs_dir
    if not raw_dir.exists():
        return set()
    return {
        path.name
        for path in raw_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".pdf"
    }


def _get_embedding_model(model_name: str):
    if model_name not in _EMBEDDING_MODELS:
        from sentence_transformers import SentenceTransformer

        _EMBEDDING_MODELS[model_name] = SentenceTransformer(model_name)
    return _EMBEDDING_MODELS[model_name]


def _normalize_matrix(matrix):
    import numpy as np

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return matrix / norms


def build_vector_index(chunks: list[TextChunk], settings: Settings) -> dict[str, Any]:
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    settings.vector_db_dir.mkdir(parents=True, exist_ok=True)
    save_chunks(chunks, settings.processed_chunks_path)

    summary: dict[str, Any] = {
        "chunk_count": len(chunks),
        "chunks_path": str(settings.processed_chunks_path),
        "embeddings_path": str(settings.embeddings_path),
        "embedding_model": settings.embedding_model,
        "embeddings_built": False,
    }

    if not chunks:
        return summary

    try:
        import numpy as np

        model = _get_embedding_model(settings.embedding_model)
        texts = [f"passage: {chunk.content}" for chunk in chunks]
        batch_size = max(1, int(os.getenv("EMBEDDING_BATCH_SIZE", "8")))
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
        )
        embeddings = _normalize_matrix(embeddings)
        np.save(settings.embeddings_path, embeddings)
        settings.embeddings_meta_path.write_text(
            json.dumps(
                {
                    "embedding_model": settings.embedding_model,
                    "chunk_count": len(chunks),
                    "chunk_ids": [chunk.chunk_id for chunk in chunks],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summary["embeddings_built"] = True
        if settings.vector_db_type == "pgvector":
            _replace_pgvector_index(chunks, embeddings, settings)
            summary["pgvector_built"] = True
    except Exception as exc:
        logger.warning("Failed to build embeddings; retrieval will use lexical fallback.", exc_info=True)
        summary["embedding_error"] = str(exc)
        if settings.vector_db_type == "pgvector":
            summary["pgvector_built"] = False
            summary["pgvector_error"] = str(exc)

    if settings.vector_db_type == "faiss":
        try:
            faiss_path = build_faiss_index(chunks, settings)
            summary["faiss_built"] = True
            summary["faiss_path"] = str(faiss_path)
        except Exception as exc:
            logger.warning("Failed to build FAISS index; local JSON vector store remains usable.", exc_info=True)
            summary["faiss_built"] = False
            summary["faiss_error"] = str(exc)

    return summary


def _vector_literal(values) -> str:
    return "[" + ",".join(f"{float(value):.9g}" for value in values) + "]"


def _replace_pgvector_index(chunks: list[TextChunk], embeddings, settings: Settings) -> None:
    """Replace the external vector index in one PostgreSQL transaction."""
    if not settings.database_url.startswith(("postgres://", "postgresql://")):
        raise RuntimeError("VECTOR_DB_TYPE=pgvector memerlukan DATABASE_URL PostgreSQL")
    import psycopg

    dimension = int(embeddings.shape[1])
    with psycopg.connect(settings.database_url) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        connection.execute(
            f"""CREATE TABLE IF NOT EXISTS knowledge_chunks (
                chunk_id VARCHAR(180) PRIMARY KEY,
                content TEXT NOT NULL,
                document_title TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                embedding vector({dimension}) NOT NULL
            )"""
        )
        existing_dimension = connection.execute(
            """SELECT atttypmod
               FROM pg_attribute
               WHERE attrelid = 'knowledge_chunks'::regclass AND attname = 'embedding'"""
        ).fetchone()
        if existing_dimension and int(existing_dimension[0]) not in {-1, dimension}:
            raise RuntimeError("Dimensi pgvector berbeda; hapus tabel knowledge_chunks sebelum mengganti model embedding")
        connection.execute("DELETE FROM knowledge_chunks")
        rows = [
            (
                chunk.chunk_id,
                chunk.content,
                chunk.document_title,
                chunk.page_number,
                chunk.file_name,
                _vector_literal(embedding),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO knowledge_chunks
                   (chunk_id, content, document_title, page_number, file_name, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s::vector)""",
                rows,
            )


def _faiss_index_dir(settings: Settings):
    return settings.vector_db_dir / "faiss_index"


def _chunk_to_langchain_document(chunk: TextChunk):
    from langchain_core.documents import Document

    return Document(
        page_content=chunk.content,
        metadata={
            "chunk_id": chunk.chunk_id,
            "document_title": chunk.document_title,
            "page_number": chunk.page_number,
            "file_name": chunk.file_name,
        },
    )


def build_faiss_index(chunks: list[TextChunk], settings: Settings):
    if not chunks:
        raise ValueError("Tidak ada chunk untuk dibuat menjadi index FAISS.")

    from langchain_community.vectorstores import FAISS

    index_dir = _faiss_index_dir(settings)
    index_dir.mkdir(parents=True, exist_ok=True)
    documents = [_chunk_to_langchain_document(chunk) for chunk in chunks]
    embeddings = SentenceTransformerEmbeddings(settings.embedding_model)
    vector_store = FAISS.from_documents(documents, embeddings)
    vector_store.save_local(str(index_dir))
    return index_dir


class LocalVectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.chunks = load_chunks(settings.processed_chunks_path)
        active_files = _active_pdf_file_names(settings)
        if active_files:
            self.chunks = [
                chunk for chunk in self.chunks
                if chunk.file_name in active_files or chunk.file_name == "imc-mask-website"
            ]
        self._embeddings = None
        self._embedding_status = "missing"
        self._load_embeddings()

    def _load_embeddings(self) -> None:
        if not self.settings.embeddings_path.exists():
            self._embedding_status = "missing"
            return
        try:
            import numpy as np

            self._embeddings = np.load(self.settings.embeddings_path)
            if len(self._embeddings) != len(self.chunks):
                self._embeddings = None
                self._embedding_status = "chunk_mismatch"
                return
            self._embedding_status = "loaded"
        except Exception as exc:
            logger.warning("Failed to load embeddings from %s.", self.settings.embeddings_path, exc_info=True)
            self._embeddings = None
            self._embedding_status = f"load_failed: {exc}"

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def embedding_status(self) -> str:
        return self._embedding_status

    @property
    def available(self) -> bool:
        return bool(self.chunks)

    def retrieve(self, question: str, top_k: int) -> list[RetrievalResult]:
        if not self.chunks:
            return []

        expanded_question = _expanded_question(question)

        if self._embeddings is not None:
            try:
                import numpy as np

                model = _get_embedding_model(self.settings.embedding_model)
                query_embedding = model.encode(
                    [f"query: {expanded_question}"],
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                query_embedding = _normalize_matrix(query_embedding)[0]
                scores = np.dot(self._embeddings, query_embedding)
                candidate_count = min(len(self.chunks), max(top_k * 10, top_k))
                ranked_indexes = np.argsort(scores)[::-1][:candidate_count]
                reranked: list[RetrievalResult] = []
                for index in ranked_indexes:
                    chunk = self.chunks[int(index)]
                    semantic_score = float(scores[int(index)])
                    lexical_score = _lexical_score(expanded_question, chunk.content)
                    combined_score = min(
                        1.0,
                        max(
                            0.0,
                            (semantic_score * 0.72)
                            + (lexical_score * 0.28)
                            + _priority_bonus(question, chunk),
                        ),
                    )
                    reranked.append(RetrievalResult(chunk=chunk, score=combined_score))
                reranked.sort(key=lambda item: item.score, reverse=True)
                return reranked[:top_k]
            except Exception:
                logger.warning("Semantic retrieval failed; falling back to lexical retrieval.", exc_info=True)

        scored = [
            RetrievalResult(
                chunk=chunk,
                score=min(
                    1.0,
                    max(
                        0.0,
                        _lexical_score(expanded_question, chunk.content) + _priority_bonus(question, chunk),
                    ),
                ),
            )
            for chunk in self.chunks
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


class FaissVectorStore(LocalVectorStore):
    """Optional LangChain FAISS vector store with the same reranking rules."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._faiss = None
        self._faiss_status = "missing"
        self._load_faiss()

    def _load_faiss(self) -> None:
        index_dir = _faiss_index_dir(self.settings)
        if not index_dir.exists():
            self._faiss_status = "missing"
            return
        try:
            from langchain_community.vectorstores import FAISS

            embeddings = SentenceTransformerEmbeddings(self.settings.embedding_model)
            self._faiss = FAISS.load_local(
                str(index_dir),
                embeddings,
                allow_dangerous_deserialization=True,
            )
            self._faiss_status = "loaded"
        except Exception as exc:
            logger.warning("Failed to load FAISS index from %s.", index_dir, exc_info=True)
            self._faiss = None
            self._faiss_status = f"load_failed: {exc}"

    @property
    def embedding_status(self) -> str:
        if self._faiss is not None:
            return f"faiss_{self._faiss_status}"
        return super().embedding_status

    def retrieve(self, question: str, top_k: int) -> list[RetrievalResult]:
        if self._faiss is None:
            return super().retrieve(question, top_k)
        expanded_question = _expanded_question(question)
        try:
            candidate_count = min(len(self.chunks), max(top_k * 10, top_k))
            documents_and_scores = self._faiss.similarity_search_with_score(
                expanded_question,
                k=candidate_count,
            )
            chunks_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
            reranked: list[RetrievalResult] = []
            for document, distance in documents_and_scores:
                chunk_id = document.metadata.get("chunk_id")
                chunk = chunks_by_id.get(chunk_id)
                if chunk is None:
                    continue
                semantic_score = 1 / (1 + max(float(distance), 0.0))
                lexical_score = _lexical_score(expanded_question, chunk.content)
                combined_score = min(
                    1.0,
                    max(
                        0.0,
                        (semantic_score * 0.72)
                        + (lexical_score * 0.28)
                        + _priority_bonus(question, chunk),
                    ),
                )
                reranked.append(RetrievalResult(chunk=chunk, score=combined_score))
            reranked.sort(key=lambda item: item.score, reverse=True)
            return reranked[:top_k]
        except Exception:
            logger.warning("FAISS retrieval failed; falling back to local retrieval.", exc_info=True)
            return super().retrieve(question, top_k)


class PgVectorStore(LocalVectorStore):
    """Neon/PostgreSQL pgvector retriever with a safe local fallback."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._load_remote_chunks()

    def _load_remote_chunks(self) -> None:
        """Hydrate chunk metadata from PostgreSQL when local build files are absent.

        Cloud Run has an ephemeral filesystem. The knowledge-base build runs as
        a Cloud Run Job and stores the durable index in Neon, so service
        instances must be able to start without generated JSON files baked into
        the container.
        """
        if not self.settings.database_url.startswith(("postgres://", "postgresql://")):
            return
        try:
            import psycopg
            from psycopg.rows import dict_row

            with psycopg.connect(self.settings.database_url, row_factory=dict_row) as connection:
                rows = connection.execute(
                    """SELECT chunk_id, content, document_title, page_number, file_name
                       FROM knowledge_chunks ORDER BY file_name, page_number, chunk_id"""
                ).fetchall()
            if rows:
                self.chunks = [
                    TextChunk(
                        chunk_id=row["chunk_id"],
                        content=row["content"],
                        document_title=row["document_title"],
                        page_number=int(row["page_number"]),
                        file_name=row["file_name"],
                    )
                    for row in rows
                ]
        except Exception:
            logger.warning(
                "Could not load pgvector chunk metadata; local fallback remains active.",
                exc_info=True,
            )

    @property
    def embedding_status(self) -> str:
        return "pgvector_ready" if self.chunks else "pgvector_not_built"

    def retrieve(self, question: str, top_k: int) -> list[RetrievalResult]:
        if not self.settings.database_url.startswith(("postgres://", "postgresql://")):
            logger.warning("pgvector selected without PostgreSQL; using local retrieval.")
            return super().retrieve(question, top_k)
        try:
            import psycopg
            from psycopg.rows import dict_row

            model = _get_embedding_model(self.settings.embedding_model)
            query_embedding = model.encode(
                [f"query: {_expanded_question(question)}"],
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            query_vector = _vector_literal(_normalize_matrix(query_embedding)[0])
            with psycopg.connect(self.settings.database_url, row_factory=dict_row) as connection:
                rows = connection.execute(
                    """SELECT chunk_id, content, document_title, page_number, file_name,
                              1 - (embedding <=> %s::vector) AS score
                       FROM knowledge_chunks
                       ORDER BY embedding <=> %s::vector
                       LIMIT %s""",
                    (query_vector, query_vector, max(top_k * 4, top_k)),
                ).fetchall()
            results = []
            for row in rows:
                chunk = TextChunk(
                    chunk_id=row["chunk_id"],
                    content=row["content"],
                    document_title=row["document_title"],
                    page_number=int(row["page_number"]),
                    file_name=row["file_name"],
                )
                semantic_score = float(row["score"] or 0.0)
                combined = min(
                    1.0,
                    max(
                        0.0,
                        (semantic_score * 0.72)
                        + (_lexical_score(question, chunk.content) * 0.28)
                        + _priority_bonus(question, chunk),
                    ),
                )
                results.append(RetrievalResult(chunk=chunk, score=combined))
            results.sort(key=lambda item: item.score, reverse=True)
            return results[:top_k]
        except Exception:
            logger.warning("pgvector retrieval failed; using local retrieval.", exc_info=True)
            return super().retrieve(question, top_k)


class LangChainVectorStoreRetriever:
    """Small LangChain retriever adapter around the active vector store."""

    def __init__(self, vector_store: LocalVectorStore, top_k: int):
        from langchain_core.retrievers import BaseRetriever
        from pydantic import ConfigDict

        class _Retriever(BaseRetriever):
            vector_store: Any
            top_k: int
            model_config = ConfigDict(arbitrary_types_allowed=True)

            def _get_relevant_documents(self, query: str, *, run_manager=None):
                documents = []
                for result in self.vector_store.retrieve(query, self.top_k):
                    document = _chunk_to_langchain_document(result.chunk)
                    document.metadata["score"] = result.score
                    documents.append(document)
                return documents

        self._retriever = _Retriever(vector_store=vector_store, top_k=top_k)

    def invoke(self, query: str):
        return self._retriever.invoke(query)


def make_vector_store(settings: Settings) -> LocalVectorStore:
    if settings.vector_db_type == "faiss":
        return FaissVectorStore(settings)
    if settings.vector_db_type == "pgvector":
        return PgVectorStore(settings)
    return LocalVectorStore(settings)
