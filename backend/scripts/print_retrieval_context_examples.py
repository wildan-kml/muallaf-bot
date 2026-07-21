"""Print a CLI-friendly retrieval example for thesis documentation."""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import textwrap
from pathlib import Path


os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import get_settings
from app.vector_store import make_vector_store


DEFAULT_QUESTION = "Saya ingin syahadat di Masjid Agung Sunda Kelapa, prosesnya bagaimana?"


def normalize_snippet(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def print_wrapped(label: str, value: str, width: int = 110) -> None:
    prefix = f"{label:<16}: "
    wrapped = textwrap.wrap(value, width=width, subsequent_indent=" " * len(prefix))
    if not wrapped:
        print(prefix)
        return
    print(prefix + wrapped[0])
    for line in wrapped[1:]:
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tampilkan contoh hasil retrieval konteks relevan."
    )
    parser.add_argument(
        "--question",
        default=DEFAULT_QUESTION,
        help="Pertanyaan uji untuk proses retrieval.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Jumlah konteks yang ditampilkan. Default mengikuti konfigurasi TOP_K.",
    )
    parser.add_argument(
        "--max-snippet",
        type=int,
        default=320,
        help="Panjang maksimal cuplikan teks tiap chunk.",
    )
    args = parser.parse_args()

    settings = get_settings()
    top_k = args.top_k or settings.top_k
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        with contextlib.redirect_stderr(devnull):
            vector_store = make_vector_store(settings)
            results = vector_store.retrieve(args.question, top_k=top_k)

    print("=" * 110)
    print("CONTOH HASIL RETRIEVAL KONTEKS RELEVAN")
    print("=" * 110)
    print_wrapped("Pertanyaan", args.question)
    print_wrapped("Embedding model", settings.embedding_model)
    print_wrapped("Vector DB", settings.vector_db_type)
    print_wrapped("Embedding status", vector_store.embedding_status)
    print_wrapped("Jumlah chunk", str(len(vector_store.chunks)))
    print_wrapped("Top-K", str(top_k))
    print_wrapped("Threshold", f"{settings.similarity_threshold:.2f}")
    print("-" * 110)

    if not results:
        print("Tidak ada konteks yang berhasil diambil.")
        return

    for index, result in enumerate(results, start=1):
        chunk = result.chunk
        print(f"Top-{index}")
        print_wrapped("Judul dokumen", chunk.document_title)
        print_wrapped("Halaman", str(chunk.page_number))
        print_wrapped("Nilai kemiripan", f"{result.score:.4f}")
        print_wrapped("ID chunk", chunk.chunk_id)
        print_wrapped("Cuplikan", normalize_snippet(chunk.content, args.max_snippet))
        print("-" * 110)

    print("Keterangan: nilai kemiripan dihitung dari gabungan skor semantik, lexical score, dan priority bonus domain.")


if __name__ == "__main__":
    main()
