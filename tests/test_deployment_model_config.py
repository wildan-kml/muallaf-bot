from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MODEL = "gemini-3.5-flash-lite"
RETIRED_MODEL = "gemini-2.5-flash"


class DeploymentModelConfigTests(unittest.TestCase):
    def test_modal_uses_current_evaluated_candidate(self):
        source = (ROOT / "deploy" / "modal_app.py").read_text(encoding="utf-8")
        self.assertIn(f'"GEMINI_MODEL": "{EXPECTED_MODEL}"', source)
        self.assertNotIn(f'"GEMINI_MODEL": "{RETIRED_MODEL}"', source)
        self.assertIn('modal.Secret.from_name("muallaf-bot-gemini")', source)
        self.assertEqual(source.count("secrets=[runtime_secret, generated_secret, gemini_secret]"), 2)

    def test_cloud_run_guide_uses_same_model(self):
        guide = (ROOT / "deploy" / "cloud-run" / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"GEMINI_MODEL={EXPECTED_MODEL}", guide)
        self.assertNotIn(f"GEMINI_MODEL={RETIRED_MODEL}", guide)

    def test_backend_default_and_example_are_aligned(self):
        config = (ROOT / "backend" / "app" / "config.py").read_text(encoding="utf-8")
        example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
        self.assertIn(f'os.getenv("GEMINI_MODEL", "{EXPECTED_MODEL}")', config)
        self.assertIn(f"GEMINI_MODEL={EXPECTED_MODEL}", example)


if __name__ == "__main__":
    unittest.main()
