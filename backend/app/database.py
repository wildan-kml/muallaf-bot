"""Database persistence for accounts, chat sessions, and message history.

SQLite is intentionally supported for local development and automated tests.
Production deployments should set ``DATABASE_URL`` to a PostgreSQL URL (for
example, Neon).  The SQL used here stays deliberately small and portable so
the application does not need a heavyweight ORM during startup.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat()


class Database:
    def __init__(self, database_url: str, retention_days: int = 30):
        self.database_url = database_url.strip()
        self.retention_days = max(1, retention_days)
        self.is_postgres = self.database_url.startswith(("postgres://", "postgresql://"))
        if not self.is_postgres:
            self.sqlite_path = self._sqlite_path(self.database_url)
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sqlite_path(database_url: str) -> Path:
        if database_url.startswith("sqlite:///"):
            return Path(database_url.removeprefix("sqlite:///"))
        if database_url.startswith("sqlite://"):
            return Path(database_url.removeprefix("sqlite://"))
        return Path(database_url or "data/app.db")

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.is_postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - depends on production extra
                raise RuntimeError(
                    "PostgreSQL memerlukan paket psycopg. Jalankan pip install -r requirements.txt."
                ) from exc
            connection = psycopg.connect(self.database_url, row_factory=dict_row)
        else:
            connection = sqlite3.connect(self.sqlite_path, timeout=15)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _sql(self, statement: str) -> str:
        return statement.replace("?", "%s") if self.is_postgres else statement

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()) -> None:
        with self.connect() as connection:
            connection.execute(self._sql(statement), parameters)

    def fetch_one(self, statement: str, parameters: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(self._sql(statement), parameters).fetchone()
            return dict(row) if row is not None else None

    def fetch_all(self, statement: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(self._sql(statement), parameters).fetchall()
            return [dict(row) for row in rows]

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                display_name VARCHAR(120) NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                privacy_accepted_at VARCHAR(40) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                last_login_at VARCHAR(40)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(160) NOT NULL DEFAULT 'Percakapan baru',
                created_at VARCHAR(40) NOT NULL,
                updated_at VARCHAR(40) NOT NULL,
                expires_at VARCHAR(40) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at VARCHAR(40) NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated ON chat_sessions(user_id, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_chat_sessions_expires ON chat_sessions(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id, created_at)",
        ]
        with self.connect() as connection:
            for statement in statements:
                connection.execute(statement)

    def create_user(
        self,
        username: str,
        display_name: str,
        password_hash: str,
        role: str = "user",
    ) -> dict[str, Any]:
        user_id = str(uuid4())
        now = as_utc_iso()
        self.execute(
            """INSERT INTO users
               (id, username, display_name, password_hash, role, privacy_accepted_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, display_name, password_hash, role, now, now),
        )
        return self.get_user_by_id(user_id) or {}

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM users WHERE username = ?", (username,))

    def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    def mark_login(self, user_id: str) -> None:
        self.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (as_utc_iso(), user_id))

    def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        password_hash: str | None = None,
    ) -> dict[str, Any]:
        if display_name is not None:
            self.execute(
                "UPDATE users SET display_name = ? WHERE id = ?",
                (display_name.strip(), user_id),
            )
        if password_hash is not None:
            self.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user_id),
            )
        return self.get_user_by_id(user_id) or {}

    def create_session(self, user_id: str, title: str = "Percakapan baru") -> dict[str, Any]:
        session_id = str(uuid4())
        now = utc_now()
        self.execute(
            """INSERT INTO chat_sessions
               (id, user_id, title, created_at, updated_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                user_id,
                title.strip()[:160] or "Percakapan baru",
                as_utc_iso(now),
                as_utc_iso(now),
                as_utc_iso(now + timedelta(days=self.retention_days)),
            ),
        )
        return self.get_session(session_id, user_id) or {}

    def get_session(self, session_id: str, user_id: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        self.purge_expired(user_id=user_id)
        return self.fetch_all(
            """SELECT id, title, created_at, updated_at, expires_at
               FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC""",
            (user_id,),
        )

    def delete_session(self, session_id: str, user_id: str) -> bool:
        if not self.get_session(session_id, user_id):
            return False
        self.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
        return True

    def add_message(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata_json: str = "{}",
    ) -> dict[str, Any]:
        session = self.get_session(session_id, user_id)
        if not session:
            raise LookupError("Sesi percakapan tidak ditemukan")
        message_id = str(uuid4())
        now = utc_now()
        self.execute(
            """INSERT INTO chat_messages
               (id, session_id, role, content, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (message_id, session_id, role, content, metadata_json, as_utc_iso(now)),
        )
        title = session["title"]
        if role == "user" and title == "Percakapan baru":
            title = content.replace("\n", " ").strip()[:80] or title
        self.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ?, expires_at = ? WHERE id = ?",
            (
                title,
                as_utc_iso(now),
                as_utc_iso(now + timedelta(days=self.retention_days)),
                session_id,
            ),
        )
        return {
            "id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata_json": metadata_json,
            "created_at": as_utc_iso(now),
        }

    def list_messages(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        if not self.get_session(session_id, user_id):
            raise LookupError("Sesi percakapan tidak ditemukan")
        return self.fetch_all(
            """SELECT id, session_id, role, content, metadata_json, created_at
               FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC""",
            (session_id,),
        )

    def purge_expired(self, user_id: str | None = None) -> int:
        now = as_utc_iso()
        if user_id:
            expired = self.fetch_all(
                "SELECT id FROM chat_sessions WHERE expires_at <= ? AND user_id = ?",
                (now, user_id),
            )
            self.execute(
                "DELETE FROM chat_sessions WHERE expires_at <= ? AND user_id = ?",
                (now, user_id),
            )
        else:
            expired = self.fetch_all("SELECT id FROM chat_sessions WHERE expires_at <= ?", (now,))
            self.execute("DELETE FROM chat_sessions WHERE expires_at <= ?", (now,))
        return len(expired)
