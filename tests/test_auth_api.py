import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Database
from app.main import app
from app.schemas import ChatResponse


class AuthApiTests(unittest.TestCase):
    def test_registration_login_and_protected_session_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(f"sqlite:///{Path(directory) / 'api.db'}", retention_days=30)
            with patch("app.main.database", database), patch("app.auth.Database", return_value=database), TestClient(app) as client:
                self.assertEqual(client.get("/api/sessions").status_code, 401)
                privacy = client.get("/api/privacy")
                self.assertEqual(privacy.status_code, 200)
                self.assertEqual(privacy.json()["retention_days"], 30)

                registration = client.post(
                    "/api/auth/register",
                    json={
                        "username": "pengguna_uji",
                        "display_name": "Pengguna Uji",
                        "password": "kata-sandi-uji",
                        "privacy_accepted": True,
                    },
                )
                self.assertEqual(registration.status_code, 201)
                token = registration.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}

                wrong_login = client.post(
                    "/api/auth/login",
                    json={"username": "pengguna_uji", "password": "salah"},
                )
                self.assertEqual(wrong_login.status_code, 401)
                self.assertEqual(wrong_login.json()["detail"], "Nama pengguna atau kata sandi salah")

                updated = client.patch(
                    "/api/auth/me",
                    json={"display_name": "Nama Baru"},
                    headers=headers,
                )
                self.assertEqual(updated.status_code, 200)
                self.assertEqual(updated.json()["user"]["display_name"], "Nama Baru")

                created = client.post("/api/sessions", json={"title": "Uji sesi"}, headers=headers)
                self.assertEqual(created.status_code, 201)
                session_id = created.json()["id"]
                self.assertEqual(client.get("/api/sessions", headers=headers).status_code, 200)
                self.assertEqual(
                    client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["messages"],
                    [],
                )
                self.assertEqual(client.get("/api/debug/runtime", headers=headers).status_code, 404)
                self.assertEqual(client.delete(f"/api/sessions/{session_id}", headers=headers).status_code, 204)

    def test_guest_chat_is_allowed_without_creating_a_persistent_session(self) -> None:
        class FakePipeline:
            vector_store = None

            def status(self):
                return {"mode": "test"}

            def answer(self, question, history):
                return ChatResponse(answer=f"Jawaban untuk {question}", sources=[])

        with tempfile.TemporaryDirectory() as directory:
            database = Database(f"sqlite:///{Path(directory) / 'guest.db'}", retention_days=30)
            with (
                patch("app.main.database", database),
                patch("app.auth.Database", return_value=database),
                patch("app.main.get_chatbot_pipeline", return_value=FakePipeline()),
                TestClient(app) as client,
            ):
                response = client.post("/api/chat", json={"question": "Apa itu syahadat?", "history": []})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json()["session_id"])
                self.assertEqual(database.fetch_all("SELECT * FROM chat_sessions"), [])


if __name__ == "__main__":
    unittest.main()
