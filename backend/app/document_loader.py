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


def load_pdf_pages(raw_pdfs_dir: Path) -> list[PageText]:
    if not raw_pdfs_dir.exists():
        return []

    pdf_paths = sorted(
        path for path in raw_pdfs_dir.iterdir()
        if path.is_file() and path.suffix.lower() == SUPPORTED_PDF_SUFFIX
    )

    pages: list[PageText] = []
    errors: list[str] = []
    for pdf_path in pdf_paths:
        try:
            pages.extend(_extract_with_pymupdf(pdf_path))
            continue
        except Exception as exc:
            errors.append(f"{pdf_path.name}: PyMuPDF failed: {exc}")

        try:
            pages.extend(_extract_with_pdfplumber(pdf_path))
        except Exception as exc:
            errors.append(f"{pdf_path.name}: pdfplumber failed: {exc}")

    if errors and not pages:
        joined = "; ".join(errors)
        raise RuntimeError(f"No PDF text could be extracted. {joined}")

    return pages
