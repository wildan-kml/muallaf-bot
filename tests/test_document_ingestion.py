import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.document_loader import load_pdf_pages
from app.preprocessing import PageText, chunk_pages, clean_document_text


class DocumentIngestionTests(unittest.TestCase):
    def test_arabic_words_keep_spaces_and_line_order(self) -> None:
        cleaned = clean_document_text("قال رسول الله\nما حق الجار")

        self.assertEqual(cleaned, "قال رسول الله ما حق الجار")
        self.assertNotIn("قالرسول", cleaned)

    def test_unverified_pdf_arabic_is_not_written_to_retrieval_chunks(self) -> None:
        page = PageText(
            "rujukan.pdf",
            "Dokumen Rujukan",
            1,
            "Penjelasan hak tetangga untuk pembinaan mualaf. قال رسول الله ما حق الجار "
            "Uraian Indonesia tetap dapat dicari dan digunakan dengan aman dalam jawaban.",
        )

        chunks = chunk_pages([page], chunk_size=300, overlap=0)

        self.assertEqual(len(chunks), 1)
        self.assertNotRegex(chunks[0].content, r"[\u0600-\u06FF]")
        self.assertIn("Uraian Indonesia", chunks[0].content)

    def test_one_unreadable_pdf_aborts_the_complete_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            good = raw / "good.pdf"
            bad = raw / "bad.pdf"
            good.write_bytes(b"%PDF-good")
            bad.write_bytes(b"%PDF-bad")

            def extract(path: Path):
                if path.name == "bad.pdf":
                    raise ValueError("corrupt")
                return [PageText(path.name, path.stem, 1, "isi dokumen")]

            with patch("app.document_loader._extract_with_pymupdf", side_effect=extract), patch(
                "app.document_loader._extract_with_pdfplumber", side_effect=ValueError("corrupt")
            ):
                with self.assertRaisesRegex(RuntimeError, "ekstraksi PDF tidak lengkap"):
                    load_pdf_pages(raw)


if __name__ == "__main__":
    unittest.main()

