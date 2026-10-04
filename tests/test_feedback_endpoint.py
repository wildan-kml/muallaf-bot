import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import _feedback_attempts, submit_feedback
from app.schemas import FeedbackRequest


class FeedbackEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        _feedback_attempts.clear()

    @staticmethod
    def make_request(ip: str = "203.0.113.10") -> Request:
        return Request({"type": "http", "headers": [], "client": (ip, 12345)})

    def test_feedback_is_emailed_and_saved_with_optional_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            backend_root = Path(temporary_directory)
            test_settings = SimpleNamespace(
                backend_root=backend_root,
                smtp_host="smtp.example.test",
                smtp_port=587,
                smtp_username="sender@example.test",
                smtp_password="app-password",
                smtp_from_email="sender@example.test",
                feedback_recipient="mwildankamil@gmail.com",
                feedback_subject="Feedback Muallaf Bot",
                feedback_rate_limit_seconds=900,
                trust_proxy_headers=False,
            )
            request = FeedbackRequest(
                identity=None,
                email="pengguna@example.com",
                feedback="  Tampilan mobile sudah lebih mudah digunakan.  ",
            )

            with patch("app.main.settings", test_settings), patch("app.main.smtplib.SMTP") as smtp_class:
                response = submit_feedback(self.make_request(), request)

            self.assertEqual(response.status, "ok")
            feedback_path = backend_root / "data" / "feedback" / "feedback.jsonl"
            record = json.loads(feedback_path.read_text(encoding="utf-8").strip())
            self.assertIsNone(record["identity"])
            self.assertEqual(record["email"], "pengguna@example.com")
            self.assertEqual(record["feedback"], "Tampilan mobile sudah lebih mudah digunakan.")
            self.assertTrue(record["id"])
            self.assertTrue(record["submitted_at"])
            smtp = smtp_class.return_value.__enter__.return_value
            smtp.login.assert_called_once_with("sender@example.test", "app-password")
            sent_message = smtp.send_message.call_args.args[0]
            self.assertEqual(sent_message["To"], "mwildankamil@gmail.com")
            self.assertEqual(sent_message["Subject"], "Feedback Muallaf Bot")
            self.assertEqual(sent_message["Reply-To"], "pengguna@example.com")
            self.assertIn("Tampilan mobile sudah lebih mudah digunakan.", sent_message.get_content())

    def test_feedback_reports_missing_smtp_configuration(self) -> None:
        settings_without_smtp = SimpleNamespace(
            backend_root=ROOT / "backend",
            smtp_username="",
            smtp_password="",
            smtp_from_email="",
        )
        request = FeedbackRequest(email="pengguna@example.com", feedback="Masukan untuk Muallaf Bot")

        with patch("app.main.settings", settings_without_smtp):
            with self.assertRaises(HTTPException) as raised:
                submit_feedback(self.make_request(), request)

        self.assertEqual(raised.exception.status_code, 503)

    def test_feedback_requires_a_valid_email_address(self) -> None:
        with self.assertRaises(ValidationError):
            FeedbackRequest(feedback="Masukan tanpa email")
        with self.assertRaises(ValidationError):
            FeedbackRequest(email="bukan-email", feedback="Masukan dengan email tidak valid")

    def test_feedback_is_limited_to_one_attempt_per_ip_in_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            test_settings = SimpleNamespace(
                backend_root=Path(temporary_directory),
                smtp_host="smtp.example.test",
                smtp_port=587,
                smtp_username="sender@example.test",
                smtp_password="app-password",
                smtp_from_email="sender@example.test",
                feedback_recipient="mwildankamil@gmail.com",
                feedback_subject="Feedback Muallaf Bot",
                feedback_rate_limit_seconds=900,
                trust_proxy_headers=False,
            )
            request = FeedbackRequest(email="pengguna@example.com", feedback="Masukan pertama")

            with patch("app.main.settings", test_settings), patch("app.main.smtplib.SMTP"):
                submit_feedback(self.make_request("203.0.113.20"), request)
                with self.assertRaises(HTTPException) as raised:
                    submit_feedback(self.make_request("203.0.113.20"), request)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("Retry-After", raised.exception.headers)


if __name__ == "__main__":
    unittest.main()
