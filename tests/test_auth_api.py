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


if __name__ == "__main__":
    unittest.main()
