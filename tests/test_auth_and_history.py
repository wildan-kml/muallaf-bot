import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import create_access_token, decode_access_token, hash_password, verify_password
from app.database import Database, as_utc_iso, utc_now


class AuthenticationAndHistoryTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verifiable(self) -> None:
        first = hash_password("rahasia-yang-panjang")
        second = hash_password("rahasia-yang-panjang")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("rahasia-yang-panjang", first))
        self.assertFalse(verify_password("password-salah", first))

    def test_signed_token_rejects_tampering(self) -> None:
        token = create_access_token("user-1", "pengguna", "secret-for-test", 30)
        self.assertEqual(decode_access_token(token, "secret-for-test")["sub"], "user-1")
        with self.assertRaises(Exception):
            decode_access_token(token[:-1] + ("a" if token[-1] != "a" else "b"), "secret-for-test")

    def test_sessions_are_isolated_and_expired_sessions_are_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(f"sqlite:///{Path(directory) / 'test.db'}", retention_days=30)
            database.initialize()
            first = database.create_user("user1", "User One", hash_password("password-user-1"))
            second = database.create_user("user2", "User Two", hash_password("password-user-2"))
            session = database.create_session(first["id"])
            database.add_message(session["id"], first["id"], "user", "Apa itu wudu?")

            self.assertEqual(len(database.list_messages(session["id"], first["id"])), 1)
            with self.assertRaises(LookupError):
                database.list_messages(session["id"], second["id"])

            database.execute(
                "UPDATE chat_sessions SET expires_at = ? WHERE id = ?",
                (as_utc_iso(utc_now() - timedelta(minutes=1)), session["id"]),
            )
            self.assertEqual(database.purge_expired(), 1)
            self.assertIsNone(database.get_session(session["id"], first["id"]))


if __name__ == "__main__":
    unittest.main()

