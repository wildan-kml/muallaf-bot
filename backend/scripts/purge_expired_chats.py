"""Delete chat sessions past the configured retention period."""

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.database import Database


def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url, settings.chat_retention_days)
    database.initialize()
    deleted = database.purge_expired()
    print(f"Expired chat sessions deleted: {deleted}")


if __name__ == "__main__":
    main()

