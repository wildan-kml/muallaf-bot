from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    backend_root: Path
    frontend_origin: str
    cors_origins: list[str]
    raw_pdfs_dir: Path
    processed_dir: Path
    vector_db_dir: Path
    vector_db_type: str
    processed_chunks_path: Path
    embeddings_path: Path
    embeddings_meta_path: Path
    embedding_model: str
    llm_provider: str
    groq_api_key: str
    groq_model: str
    gemini_api_key: str
    gemini_model: str
    ollama_base_url: str
    ollama_model: str
    top_k: int
    similarity_threshold: float
    chunk_size: int
    chunk_overlap: int
    rag_engine: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    feedback_recipient: str
    feedback_subject: str
    feedback_rate_limit_seconds: int
    trust_proxy_headers: bool
    origin_shared_secret: str
    max_request_body_bytes: int
    guest_chat_rate_per_minute: int
    user_chat_rate_per_minute: int
    global_chat_rate_per_minute: int
    login_rate_per_ten_minutes: int
    registration_rate_per_hour: int
    database_url: str
    jwt_secret: str
    access_token_minutes: int
    chat_retention_days: int
    allow_registration: bool
    debug_endpoint_enabled: bool
    environment: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file(BACKEND_ROOT / ".env")

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    cors_origins = _get_list(
        "CORS_ORIGINS",
        [
            frontend_origin,
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
    )

    raw_pdfs_dir = BACKEND_ROOT / "data" / "raw_pdfs"
    processed_dir = BACKEND_ROOT / "data" / "processed"
    vector_db_dir = BACKEND_ROOT / "data" / "vector_db"

    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    database_url = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(BACKEND_ROOT / 'data' / 'app.db').as_posix()}",
    ).strip()

    return Settings(
        project_root=PROJECT_ROOT,
        backend_root=BACKEND_ROOT,
        frontend_origin=frontend_origin,
        cors_origins=cors_origins,
        raw_pdfs_dir=raw_pdfs_dir,
        processed_dir=processed_dir,
        vector_db_dir=vector_db_dir,
        vector_db_type=os.getenv("VECTOR_DB_TYPE", "local_json").strip().lower(),
        processed_chunks_path=processed_dir / "chunks.json",
        embeddings_path=vector_db_dir / "embeddings.npy",
        embeddings_meta_path=vector_db_dir / "embeddings_meta.json",
        embedding_model=os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small"),
        llm_provider=os.getenv("LLM_PROVIDER", "gemini").strip().lower(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        top_k=_get_int("TOP_K", 4),
        similarity_threshold=_get_float("SIMILARITY_THRESHOLD", 0.30),
        chunk_size=_get_int("CHUNK_SIZE", 900),
        chunk_overlap=_get_int("CHUNK_OVERLAP", 120),
        rag_engine=os.getenv("RAG_ENGINE", "langchain").strip().lower(),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        smtp_port=_get_int("SMTP_PORT", 587),
        smtp_username=smtp_username,
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from_email=os.getenv("SMTP_FROM_EMAIL", smtp_username).strip(),
        feedback_recipient=os.getenv("FEEDBACK_RECIPIENT", "mwildankamil@gmail.com").strip(),
        feedback_subject=os.getenv("FEEDBACK_SUBJECT", "Feedback Muallaf Bot").strip(),
        feedback_rate_limit_seconds=max(60, _get_int("FEEDBACK_RATE_LIMIT_SECONDS", 900)),
        trust_proxy_headers=os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() in {"1", "true", "yes"},
        origin_shared_secret=os.getenv("ORIGIN_SHARED_SECRET", "").strip(),
        max_request_body_bytes=max(4096, _get_int("MAX_REQUEST_BODY_BYTES", 65536)),
        guest_chat_rate_per_minute=max(1, _get_int("GUEST_CHAT_RATE_PER_MINUTE", 6)),
        user_chat_rate_per_minute=max(1, _get_int("USER_CHAT_RATE_PER_MINUTE", 15)),
        global_chat_rate_per_minute=max(1, _get_int("GLOBAL_CHAT_RATE_PER_MINUTE", 30)),
        login_rate_per_ten_minutes=max(1, _get_int("LOGIN_RATE_PER_TEN_MINUTES", 10)),
        registration_rate_per_hour=max(1, _get_int("REGISTRATION_RATE_PER_HOUR", 3)),
        database_url=database_url,
        jwt_secret=os.getenv("JWT_SECRET", "change-this-development-secret").strip(),
        access_token_minutes=max(15, _get_int("ACCESS_TOKEN_MINUTES", 480)),
        chat_retention_days=max(1, _get_int("CHAT_RETENTION_DAYS", 30)),
        allow_registration=os.getenv("ALLOW_REGISTRATION", "true").strip().lower() in {"1", "true", "yes"},
        debug_endpoint_enabled=os.getenv("DEBUG_ENDPOINT_ENABLED", "false").strip().lower() in {"1", "true", "yes"},
        environment=os.getenv("APP_ENV", "development").strip().lower(),
    )
