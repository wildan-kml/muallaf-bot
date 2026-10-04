import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import download_document


class DocumentDownloadTests(unittest.TestCase):
    def test_pdf_is_returned_as_an_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_pdfs_dir = Path(temporary_directory)
            pdf_path = raw_pdfs_dir / "Modul Pembinaan Mualaf.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 test")

            with patch("app.main.settings", SimpleNamespace(raw_pdfs_dir=raw_pdfs_dir)):
                response = download_document(pdf_path.name)

            self.assertEqual(Path(response.path), pdf_path)
            self.assertEqual(response.media_type, "application/pdf")
            self.assertIn("attachment", response.headers["content-disposition"])

    def test_download_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = SimpleNamespace(raw_pdfs_dir=Path(temporary_directory))
            with patch("app.main.settings", settings):
                with self.assertRaises(HTTPException) as raised:
                    download_document("../rahasia.pdf")

            self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
