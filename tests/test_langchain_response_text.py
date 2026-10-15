import unittest
from types import SimpleNamespace

from app.langchain_pipeline import _response_text


class LangChainResponseTextTests(unittest.TestCase):
    def test_plain_string_content(self):
        response = SimpleNamespace(content="Jawaban biasa.")
        self.assertEqual(_response_text(response), "Jawaban biasa.")

    def test_structured_text_blocks(self):
        response = SimpleNamespace(
            content=[
                {"type": "text", "text": "Paragraf pertama."},
                {"type": "text", "text": "Paragraf kedua."},
            ]
        )
        self.assertEqual(_response_text(response), "Paragraf pertama.\nParagraf kedua.")

    def test_empty_structured_content(self):
        response = SimpleNamespace(content=[{"type": "metadata", "value": "ignored"}])
        self.assertIsNone(_response_text(response))


if __name__ == "__main__":
    unittest.main()
