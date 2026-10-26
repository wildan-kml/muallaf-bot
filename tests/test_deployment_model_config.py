from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MODEL = "gemini-3.5-flash-lite"
EXPECTED_GROQ_MODEL = "openai/gpt-oss-120b"
RETIRED_MODELS = ("gemini-2.5-flash", "gemini-3.1-flash-lite")


class DeploymentModelConfigTests(unittest.TestCase):
    def test_modal_uses_current_evaluated_candidate(self):
        source = (ROOT / "deploy" / "modal_app.py").read_text(encoding="utf-8")
        self.assertIn(f'"GEMINI_MODEL": "{EXPECTED_MODEL}"', source)
        for retired_model in RETIRED_MODELS:
            self.assertNotIn(f'"GEMINI_MODEL": "{retired_model}"', source)
        self.assertIn('modal.Secret.from_name("muallaf-bot-gemini")', source)
        self.assertIn('modal.Secret.from_name("muallaf-bot-groq")', source)
        self.assertEqual(source.count("secrets=[runtime_secret, generated_secret, groq_secret, gemini_secret]"), 4)

    def test_cloud_run_guide_uses_same_model(self):
        guide = (ROOT / "deploy" / "cloud-run" / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"GEMINI_MODEL={EXPECTED_MODEL}", guide)
        for retired_model in RETIRED_MODELS:
            self.assertNotIn(f"GEMINI_MODEL={retired_model}", guide)

    def test_backend_default_and_example_are_aligned(self):
        config = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
        example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
        self.assertIn(f'os.getenv("GEMINI_MODEL", "{EXPECTED_MODEL}")', config)
        self.assertIn(f"GEMINI_MODEL={EXPECTED_MODEL}", example)
        self.assertIn(f'os.getenv("GROQ_MODEL", "{EXPECTED_GROQ_MODEL}")', config)
        self.assertIn(f"GROQ_MODEL={EXPECTED_GROQ_MODEL}", example)


if __name__ == "__main__":
    unittest.main()
