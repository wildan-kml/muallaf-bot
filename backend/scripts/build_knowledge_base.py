from pathlib import Path
import sys
from dataclasses import replace
import json
import os
import tempfile


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.document_loader import load_pdf_pages
from app.preprocessing import build_imc_mask_website_chunks, chunk_pages
from app.vector_store import build_vector_index


def main() -> None:
    settings = get_settings()
    settings.raw_pdfs_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    settings.vector_db_dir.mkdir(parents=True, exist_ok=True)

    pages = load_pdf_pages(settings.raw_pdfs_dir)
    chunks = chunk_pages(
        pages,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    chunks.extend(build_imc_mask_website_chunks())
    # Build into an isolated staging directory.  Nothing in the active
    # knowledge base is replaced until every PDF and embedding succeeds.
    with tempfile.TemporaryDirectory(prefix="muallaf-kb-") as temporary_directory:
        staging_root = Path(temporary_directory)
        staging_processed = staging_root / "processed"
        staging_vector = staging_root / "vector_db"
        staging_settings = replace(
            settings,
            processed_dir=staging_processed,
            vector_db_dir=staging_vector,
            processed_chunks_path=staging_processed / "chunks.json",
            embeddings_path=staging_vector / "embeddings.npy",
            embeddings_meta_path=staging_vector / "embeddings_meta.json",
        )
        summary = build_vector_index(chunks, staging_settings)
        if not summary.get("embeddings_built"):
            raise RuntimeError(
                "Knowledge base build dibatalkan karena embeddings gagal. "
                "Index aktif sebelumnya tidak diubah."
            )
        if settings.vector_db_type == "pgvector" and not summary.get("pgvector_built"):
            raise RuntimeError(
                "Knowledge base build dibatalkan karena sinkronisasi pgvector gagal. "
                "Index eksternal aktif sebelumnya tidak diubah."
            )

        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        settings.vector_db_dir.mkdir(parents=True, exist_ok=True)
        os.replace(staging_settings.processed_chunks_path, settings.processed_chunks_path)
        os.replace(staging_settings.embeddings_path, settings.embeddings_path)
        os.replace(staging_settings.embeddings_meta_path, settings.embeddings_meta_path)
        manifest = {
            "status": "complete",
            "documents": sorted({page.file_name for page in pages}),
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "embedding_model": settings.embedding_model,
        }
        (settings.processed_dir / "build_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary.update(
            chunks_path=str(settings.processed_chunks_path),
            embeddings_path=str(settings.embeddings_path),
        )

    documents = sorted({page.file_name for page in pages})
    synthetic_documents = ["Website International Muallaf Center Masjid Agung Sunda Kelapa (IMC-MASK)"]
    print("IMC-MASK RAG knowledge base build complete")
    print(f"Raw PDF folder     : {settings.raw_pdfs_dir}")
    print(f"Documents found    : {len(documents) + len(synthetic_documents)}")
    for document in documents:
        print(f"  - {document}")
    for document in synthetic_documents:
        print(f"  - {document}")
    print(f"Pages extracted    : {len(pages)}")
    print(f"Chunks generated   : {len(chunks)}")
    print(f"Chunks JSON        : {summary['chunks_path']}")
    print(f"Embedding model    : {summary['embedding_model']}")
    print(f"Embeddings built   : {summary['embeddings_built']}")
    if "faiss_built" in summary:
        print(f"FAISS built        : {summary['faiss_built']}")
        if summary.get("faiss_path"):
            print(f"FAISS index        : {summary['faiss_path']}")
        if summary.get("faiss_error"):
            print(f"FAISS warning      : {summary['faiss_error']}")
    if "pgvector_built" in summary:
        print(f"pgvector built     : {summary['pgvector_built']}")
        if summary.get("pgvector_error"):
            print(f"pgvector warning   : {summary['pgvector_error']}")
    if summary.get("embedding_error"):
        print(f"Embedding warning  : {summary['embedding_error']}")
        print("Retrieval can still run with lexical fallback, but RAG quality is lower.")


if __name__ == "__main__":
    main()
