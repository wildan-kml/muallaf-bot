from pathlib import Path
import sys


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
    summary = build_vector_index(chunks, settings)

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
    if summary.get("embedding_error"):
        print(f"Embedding warning  : {summary['embedding_error']}")
        print("Retrieval can still run with lexical fallback, but RAG quality is lower.")


if __name__ == "__main__":
    main()
