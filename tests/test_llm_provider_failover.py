import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag_pipeline import RagPipeline
from app.langchain_pipeline import LangChainRagPipeline


class LlmProviderFailoverTests(unittest.TestCase):
    def make_pipeline(self, *, groq_key="groq-key", gemini_key="gemini-key", provider="auto"):
        pipeline = RagPipeline.__new__(RagPipeline)
        pipeline.settings = SimpleNamespace(
            llm_provider=provider,
            groq_api_key=groq_key,
            gemini_api_key=gemini_key,
            ollama_base_url="http://127.0.0.1:11434",
            ollama_model="llama3.1:8b",
        )
        return pipeline

    def test_auto_prefers_gemini_then_groq(self):
        pipeline = self.make_pipeline()
        self.assertEqual(pipeline._generation_providers(), ["gemini", "groq"])

    def test_auto_skips_missing_provider_credentials(self):
        pipeline = self.make_pipeline(groq_key="")
        self.assertEqual(pipeline._generation_providers(), ["gemini"])

        pipeline = self.make_pipeline(gemini_key="")
        self.assertEqual(pipeline._generation_providers(), ["groq"])

    def test_generation_falls_through_in_order(self):
        pipeline = self.make_pipeline()
        calls = []

        def generate(provider, question, results, history=None):
            calls.append(provider)
            return None if provider == "gemini" else "Jawaban Groq"

        pipeline._try_generate_with_provider = generate
        answer = pipeline._generate_answer("Pertanyaan", [])

        self.assertEqual(answer, "Jawaban Groq")
        self.assertEqual(calls, ["gemini", "groq"])

    def test_langchain_retries_overconservative_context_refusal(self):
        pipeline = LangChainRagPipeline.__new__(LangChainRagPipeline)
        calls = []
        pipeline._generation_providers = lambda: ["gemini", "groq"]

        def generate(provider, question, results, history=None):
            calls.append(provider)
            if provider == "gemini":
                return "Konteks dokumen belum menyediakan informasi lengkap mengenai hal tersebut."
            return "Mulailah dari ibadah kecil yang konsisten setiap hari."

        pipeline._try_generate_with_provider = generate
        answer = pipeline._generate_answer("Bagaimana menjaga kebiasaan ibadah?", [])

        self.assertEqual(answer, "Mulailah dari ibadah kecil yang konsisten setiap hari.")
        self.assertEqual(calls, ["gemini", "groq"])


if __name__ == "__main__":
    unittest.main()
