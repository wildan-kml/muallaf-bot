import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import create_access_token, decode_access_token
from app.schemas import ChatRequest
from app.security import ApiSecurityMiddleware, SlidingWindowRateLimiter


class SecurityControlTests(unittest.TestCase):
    def test_production_origin_secret_and_body_limit(self) -> None:
        protected = FastAPI()

        @protected.post("/api/test")
        async def echo(payload: dict) -> dict:
            return payload

        protected.add_middleware(
            ApiSecurityMiddleware,
            environment="production",
            origin_secret="s" * 32,
            max_body_bytes=64,
        )
        with TestClient(protected) as client:
            self.assertEqual(client.post("/api/test", json={"ok": True}).status_code, 403)
            headers = {"X-Origin-Verify": "s" * 32}
            self.assertEqual(client.post("/api/test", json={"ok": True}, headers=headers).status_code, 200)
            self.assertEqual(client.post("/api/test", content=b"x" * 65, headers=headers).status_code, 413)

    def test_rate_limiter_returns_retry_after(self) -> None:
        limiter = SlidingWindowRateLimiter()
        limiter.claim("same-user", 1, 60, "Terlalu banyak")
        with self.assertRaises(Exception) as context:
            limiter.claim("same-user", 1, 60, "Terlalu banyak")
        self.assertEqual(context.exception.status_code, 429)
        self.assertIn("Retry-After", context.exception.headers)

    def test_chat_history_is_limited_to_six_messages(self) -> None:
        payload = {"question": "Tes", "history": [{"role": "user", "text": "x"}] * 7}
        with self.assertRaises(Exception):
            ChatRequest.model_validate(payload)

    def test_jwt_rejects_modified_algorithm_header(self) -> None:
        token = create_access_token("user-id", "user", "secret" * 8, 60)
        header, payload, signature = token.split(".")
        with self.assertRaises(Exception):
            decode_access_token(f"e30.{payload}.{signature}", "secret" * 8)


if __name__ == "__main__":
    unittest.main()
