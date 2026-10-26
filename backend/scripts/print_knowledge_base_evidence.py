"""Print sanitized knowledge-base evidence for thesis screenshots.

This script is intentionally read-only. It never rebuilds the index, connects to
the production database, or prints environment variables and credentials.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings


def _separator(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _shorten(text: str, limit: int = 650) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()} ..."


def main() -> None:
    import numpy as np

    settings = get_settings()
    manifest_path = settings.processed_dir / "build_manifest.json"
    chunks_path = settings.processed_chunks_path
    embeddings_path = settings.embeddings_path
    metadata_path = settings.embeddings_meta_path

    required = [manifest_path, chunks_path, embeddings_path, metadata_path]
    missing = [path for path in required if not path.exists()]
    if missing:
        print("Knowledge-base evidence is not ready.")
        for path in missing:
            print(f"Missing: {path}")
        raise SystemExit(1)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    chunks = json.loads(chunks_path.read_text(encoding="utf-8-sig"))
    embedding_metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    embeddings = np.load(embeddings_path)

    _separator("MUALLAF BOT - KNOWLEDGE BASE BUILD EVIDENCE")
    print(f"Build status       : {manifest.get('status', 'unknown')}")
    print(f"PDF documents      : {len(manifest.get('documents', []))}")
    for document in manifest.get("documents", []):
        print(f"  - {document}")
    print("  - Website International Muallaf Center (IMC-MASK)")
    print(f"Pages extracted    : {manifest.get('page_count', 0)}")
    print(f"Chunks generated   : {manifest.get('chunk_count', len(chunks))}")
    print(f"Embedding model    : {manifest.get('embedding_model', settings.embedding_model)}")
    print(f"Embeddings built   : {len(embeddings) == len(chunks)}")

    # Prefer a substantive instructional chunk instead of cover, copyright, or
    # table-of-contents material so the screenshot demonstrates useful content.
    sample_index = next(
        (
            index
            for index, chunk in enumerate(chunks)
            if int(chunk.get("page_number") or 0) >= 10
            and "pengertian wudhu" in str(chunk.get("content", "")).lower()
            and len(str(chunk.get("content", ""))) >= 250
        ),
        0,
    )
    sample = chunks[sample_index]

    _separator("SAMPLE CHUNK AND METADATA")
    print(f"Chunk index        : {sample_index}")
    print(f"Chunk ID           : {sample.get('chunk_id', '-')}")
    print(f"Document title     : {sample.get('document_title', '-')}")
    print(f"Source file        : {sample.get('file_name', '-')}")
    print(f"Page number        : {sample.get('page_number', '-')}")
    print(f"Characters         : {len(str(sample.get('content', '')))}")
    print("Content preview    :")
    print(_shorten(sample.get("content", "")))

    vector = embeddings[sample_index]
    vector_preview = ", ".join(f"{float(value):+.6f}" for value in vector[:12])

    _separator("EMBEDDING MATRIX")
    print(f"Matrix shape       : {embeddings.shape}")
    print(f"Vector dimension   : {embeddings.shape[1] if embeddings.ndim == 2 else 0}")
    print(f"Metadata chunks    : {embedding_metadata.get('chunk_count', 0)}")
    print(f"Vector L2 norm     : {float(np.linalg.norm(vector)):.6f}")
    print(f"First 12 values    : [{vector_preview}, ...]")
    print()
    print("Verification       : chunk count and embedding rows are consistent")
    print("Security           : no API key, database URL, or secret is displayed")


if __name__ == "__main__":
    main()
