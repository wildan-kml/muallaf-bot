import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Database
from app.main import app, _conversation_title
from app.schemas import ChatResponse


class AuthApiTests(unittest.TestCase):
    def test_conversation_title_uses_topic_instead_of_placeholder(self) -> None:
        self.assertEqual(
            _conversation_title("Jelaskan tata cara sholat", "Jawaban panjang"),
            "Tata cara sholat",
        )
        self.assertNotEqual(
            _conversation_title("ss", "Penjelasan tentang wudu untuk pemula."),
            "Ss",
        )

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
                self.assertEqual(wrong_login.json()["detail"], "Nama lengkap/nama pengguna atau kata sandi salah")

                full_name_login = client.post(
                    "/api/auth/login",
                    json={"username": "Pengguna Uji", "password": "kata-sandi-uji"},
                )
                self.assertEqual(full_name_login.status_code, 200)

                updated = client.patch(
                    "/api/auth/me",
                    json={"display_name": "Nama Baru"},
                    headers=headers,
                )
                self.assertEqual(updated.status_code, 200)
                self.assertEqual(updated.json()["user"]["display_name"], "Nama Baru")

                mismatched_password = client.patch(
                    "/api/auth/me",
                    json={
                        "current_password": "kata-sandi-uji",
                        "new_password": "kata-sandi-baru",
                        "new_password_confirm": "tidak-sama-123",
                    },
                    headers=headers,
                )
                self.assertEqual(mismatched_password.status_code, 422)

                created = client.post("/api/sessions", json={"title": "Uji sesi"}, headers=headers)
                self.assertEqual(created.status_code, 201)
                session_id = created.json()["id"]
                self.assertEqual(client.get("/api/sessions", headers=headers).status_code, 200)
                self.assertEqual(
                    client.get(f"/api/sessions/{session_id}/messages", headers=headers).json()["messages"],
                    [],
                )
                renamed = client.patch(
                    f"/api/sessions/{session_id}",
                    json={"title": "Judul yang diubah"},
                    headers=headers,
                )
                self.assertEqual(renamed.status_code, 200)
                self.assertEqual(renamed.json()["title"], "Judul yang diubah")

                imported = client.post(
                    "/api/sessions/import",
                    json={
                        "messages": [
                            {"role": "user", "text": "Bagaimana belajar wudu?"},
                            {"role": "bot", "text": "Belajar wudu dapat dilakukan secara bertahap."},
                        ]
                    },
                    headers=headers,
                )
                self.assertEqual(imported.status_code, 201)
                imported_messages = client.get(
                    f"/api/sessions/{imported.json()['id']}/messages",
                    headers=headers,
                ).json()["messages"]
                self.assertEqual(len(imported_messages), 2)

                class FakePipeline:
                    def answer(self, question, history):
                        return ChatResponse(
                            answer="Salat dipelajari bertahap mulai dari bersuci, gerakan, dan bacaan.",
                            sources=[],
                        )

                with patch("app.main.get_chatbot_pipeline", return_value=FakePipeline()):
                    first_chat = client.post(
                        "/api/chat",
                        json={"question": "Jelaskan tata cara salat", "history": []},
                        headers=headers,
                    )
                self.assertEqual(first_chat.status_code, 200)
                generated_session_id = first_chat.json()["session_id"]
                generated_session = next(
                    item for item in client.get("/api/sessions", headers=headers).json()["sessions"]
                    if item["id"] == generated_session_id
                )
                self.assertEqual(generated_session["title"], "Tata cara salat")
                self.assertEqual(generated_session["message_count"], 2)

                self.assertEqual(client.get("/api/debug/runtime", headers=headers).status_code, 404)
                self.assertEqual(client.delete(f"/api/sessions/{session_id}", headers=headers).status_code, 204)

                wrong_delete = client.request(
                    "DELETE",
                    "/api/auth/me",
                    json={"username": "bukan_pengguna"},
                    headers=headers,
                )
                self.assertEqual(wrong_delete.status_code, 422)
                deleted = client.request(
                    "DELETE",
                    "/api/auth/me",
                    json={"username": "pengguna_uji"},
                    headers=headers,
                )
                self.assertEqual(deleted.status_code, 204)
                self.assertEqual(client.get("/api/auth/me", headers=headers).status_code, 401)

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
