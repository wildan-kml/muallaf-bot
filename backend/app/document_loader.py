from pathlib import Path

from .preprocessing import PageText, clean_document_text, normalize_document_title


SUPPORTED_PDF_SUFFIX = ".pdf"


def _extract_with_pymupdf(pdf_path: Path) -> list[PageText]:
    import fitz

    pages: list[PageText] = []
    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document, start=1):
            text = clean_document_text(page.get_text("text"))
            if text:
                pages.append(
                    PageText(
                        file_name=pdf_path.name,
                        document_title=normalize_document_title(file_name=pdf_path.name, document_title=pdf_path.stem),
                        page_number=index,
                        text=text,
                    )
                )
    return pages


def _extract_with_pdfplumber(pdf_path: Path) -> list[PageText]:
    import pdfplumber

    pages: list[PageText] = []
    with pdfplumber.open(pdf_path) as document:
        for index, page in enumerate(document.pages, start=1):
            text = clean_document_text(page.extract_text() or "")
            if text:
                pages.append(
                    PageText(
                        file_name=pdf_path.name,
                        document_title=normalize_document_title(file_name=pdf_path.name, document_title=pdf_path.stem),
                        page_number=index,
                        text=text,
                    )
                )
    return pages


def load_pdf_pages(raw_pdfs_dir: Path, *, strict: bool = True) -> list[PageText]:
    """Extract every PDF or fail the entire ingestion transaction.

    A partially built knowledge base is dangerous for a religious-information
    assistant because missing material is not visible to users.  In strict mode
    (the default), one unreadable or empty PDF aborts the build and preserves the
    previously published index.
    """
    if not raw_pdfs_dir.exists():
        return []

    pdf_paths = sorted(
        path for path in raw_pdfs_dir.iterdir()
        if path.is_file() and path.suffix.lower() == SUPPORTED_PDF_SUFFIX
    )

    pages: list[PageText] = []
    errors: list[str] = []
    for pdf_path in pdf_paths:
        extracted: list[PageText] = []
        extractor_errors: list[str] = []
        try:
            extracted = _extract_with_pymupdf(pdf_path)
        except Exception as exc:
            extractor_errors.append(f"PyMuPDF failed: {exc}")

        if not extracted:
            try:
                extracted = _extract_with_pdfplumber(pdf_path)
            except Exception as exc:
                extractor_errors.append(f"pdfplumber failed: {exc}")

        if not extracted:
            detail = "; ".join(extractor_errors) or "tidak ada teks yang dapat diekstrak"
            errors.append(f"{pdf_path.name}: {detail}")
        else:
            pages.extend(extracted)

    if errors and (strict or not pages):
        joined = "; ".join(errors)
        raise RuntimeError(f"Knowledge base build dibatalkan karena ekstraksi PDF tidak lengkap. {joined}")

    return pages
