import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.document_loader import load_pdf_pages
from app.preprocessing import PageText


class DocumentIngestionTests(unittest.TestCase):
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

