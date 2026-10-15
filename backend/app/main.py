import os
import logging
import json
import smtplib
import threading
import time
import hashlib
from ipaddress import ip_address
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .auth import (
    AuthenticatedUser,
    create_access_token,
    get_current_user,
    get_optional_user,
    hash_password,
    require_admin,
    verify_password,
)
from .database import Database
from .pipeline_factory import get_chatbot_pipeline
from .schemas import (
    AccountUpdateRequest,
    ChatRequest,
    ChatResponse,
    ChatMessage,
    FeedbackRequest,
    FeedbackResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    SessionCreateRequest,
)
from .security import ApiSecurityMiddleware, SlidingWindowRateLimiter


settings = get_settings()
database = Database(settings.database_url, settings.chat_retention_days)
logger = logging.getLogger(__name__)
_feedback_attempts: dict[str, float] = {}
_feedback_rate_limit_lock = threading.Lock()
_request_limiter = SlidingWindowRateLimiter()

for directory in (settings.raw_pdfs_dir, settings.processed_dir, settings.vector_db_dir):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="IMC-MASK API",
    version="0.3.0",
    description="API IMC-MASK untuk chatbot Muallaf Bot berbasis RAG.",
    docs_url=None if settings.environment == "production" else "/docs",
    redoc_url=None if settings.environment == "production" else "/redoc",
    openapi_url=None if settings.environment == "production" else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Origin-Verify", "X-Muallaf-Client-IP"],
)
app.add_middleware(
    ApiSecurityMiddleware,
    environment=settings.environment,
    origin_secret=settings.origin_shared_secret,
    max_body_bytes=settings.max_request_body_bytes,
)

app.mount(
    "/api/documents/files",
    StaticFiles(directory=settings.raw_pdfs_dir),
    name="document-files",
)


@app.on_event("startup")
def warmup_rag_pipeline() -> None:
    """Load RAG resources before the first user chat request.

    The first retrieval can be slow because the embedding model is loaded
    lazily. Running a tiny retrieval during startup moves that cost to backend
    boot time, so the first visible chatbot response is faster.
    """
    if settings.environment == "production":
        if settings.jwt_secret == "change-this-development-secret" or len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET produksi wajib acak dan minimal 32 karakter.")
        if len(settings.origin_shared_secret) < 32:
            raise RuntimeError("ORIGIN_SHARED_SECRET produksi wajib acak dan minimal 32 karakter.")
    database.initialize()
    database.purge_expired()
    try:
        pipeline = get_chatbot_pipeline()
        pipeline.status()
        if getattr(pipeline, "vector_store", None) and pipeline.vector_store.available:
            pipeline.vector_store.retrieve("query: syahadat mualaf", 1)
    except Exception:
        logger.warning("RAG warmup failed; the first chat request may be slower.", exc_info=True)


def get_bot_suggestions(limit: int = 6) -> list[dict[str, str]]:
    representative_questions = [
        ("Saya ingin masuk Islam, langkah awalnya apa?", "syahadat"),
        ("Apa makna dua kalimat syahadat?", "syahadat"),
        ("Apa saja materi pembinaan setelah syahadat?", "pembinaan"),
        ("Bagaimana belajar wudhu dan shalat dari awal?", "ibadah"),
        ("Bagaimana menjaga hubungan dengan keluarga yang belum Muslim?", "keluarga"),
        ("Kapan saya perlu menghubungi pembina IMC-MASK?", "pendampingan"),
    ]
    return [
        {"question": question, "intent": intent}
        for question, intent in representative_questions[:limit]
    ]


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "IMC-MASK RAG backend is running",
    }


@app.get("/api/privacy")
def privacy_notice() -> dict[str, Any]:
    return {
        "version": "2026-10-15",
        "summary": (
            "Akun berbasis nama pengguna dan riwayat percakapan disimpan untuk memulihkan sesi pengguna. "
            f"Riwayat akun dihapus otomatis {settings.chat_retention_days} hari setelah aktivitas terakhir. "
            "Percakapan tamu tidak dibuatkan sesi di database dan hanya bertahan satu jam di tab browser."
        ),
        "retention_days": settings.chat_retention_days,
        "data_collected": ["nama lengkap", "nama pengguna", "riwayat percakapan", "data teknis keamanan sementara", "feedback opsional"],
        "not_collected": ["alamat email untuk login", "password asli", "nomor identitas", "data pembayaran"],
        "user_controls": ["mengubah nama lengkap", "mengganti kata sandi", "menghapus sesi", "keluar dari akun"],
        "security_processing": "Cloudflare memproses token Turnstile, alamat jaringan, dan cookie keamanan berdurasi satu jam untuk mencegah spam dan penyalahgunaan.",
        "warning": "Jangan kirimkan kata sandi, nomor identitas, atau informasi pribadi yang tidak diperlukan.",
    }


def _public_user(user: dict[str, Any] | AuthenticatedUser) -> dict[str, str]:
    return {
        "id": str(user.id if isinstance(user, AuthenticatedUser) else user["id"]),
        "username": str(user.username if isinstance(user, AuthenticatedUser) else user["username"]),
        "display_name": str(user.display_name if isinstance(user, AuthenticatedUser) else user["display_name"]),
        "role": str(user.role if isinstance(user, AuthenticatedUser) else user["role"]),
    }


def _client_key(request: Request) -> str:
    if settings.environment == "production":
        forwarded = request.headers.get("x-muallaf-client-ip", "").strip()
        if forwarded:
            try:
                return str(ip_address(forwarded))
            except ValueError:
                pass
    return request.client.host if request.client else "unknown"


def _authorization_key(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "").strip()
    if not authorization:
        return None
    return hashlib.sha256(authorization.encode("utf-8")).hexdigest()


@app.post("/api/auth/register", response_model=LoginResponse, status_code=201)
def register(request: RegisterRequest, http_request: Request) -> LoginResponse:
    _request_limiter.claim(
        f"register:{_client_key(http_request)}",
        settings.registration_rate_per_hour,
        3600,
        "Terlalu banyak percobaan pendaftaran. Coba lagi nanti.",
    )
    if not settings.allow_registration:
        raise HTTPException(status_code=403, detail="Pendaftaran akun baru sedang ditutup")
    if not request.privacy_accepted:
        raise HTTPException(status_code=422, detail="Persetujuan privasi diperlukan")
    username = request.username.strip().lower()
    if database.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Nama pengguna sudah digunakan")
    try:
        user = database.create_user(
            username=username,
            display_name=request.display_name.strip(),
            password_hash=hash_password(request.password),
        )
    except Exception as exc:
        logger.warning("Account registration failed.", exc_info=True)
        if database.get_user_by_username(username):
            raise HTTPException(status_code=409, detail="Nama pengguna sudah digunakan") from exc
        raise HTTPException(status_code=503, detail="Akun belum dapat dibuat") from exc
    token = create_access_token(user["id"], user["username"], settings.jwt_secret, settings.access_token_minutes)
    return LoginResponse(access_token=token, token_type="bearer", user=_public_user(user))


@app.post("/api/auth/login", response_model=LoginResponse)
def login(request: LoginRequest, http_request: Request) -> LoginResponse:
    _request_limiter.claim(
        f"login:{_client_key(http_request)}:{request.username.strip().lower()}",
        settings.login_rate_per_ten_minutes,
        600,
        "Terlalu banyak percobaan masuk. Coba lagi beberapa menit.",
    )
    user = database.get_user_by_username(request.username.strip().lower())
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Nama pengguna atau kata sandi salah")
    database.mark_login(user["id"])
    token = create_access_token(user["id"], user["username"], settings.jwt_secret, settings.access_token_minutes)
    return LoginResponse(access_token=token, token_type="bearer", user=_public_user(user))


@app.get("/api/auth/me")
def current_account(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return {"user": _public_user(user)}


@app.patch("/api/auth/me")
def update_current_account(
    request: AccountUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    stored_user = database.get_user_by_id(user.id)
    if not stored_user:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if not request.display_name and not request.new_password:
        raise HTTPException(status_code=422, detail="Tidak ada perubahan akun yang dikirim")
    password_hash = None
    if request.new_password:
        if not request.current_password or not verify_password(request.current_password, stored_user["password_hash"]):
            raise HTTPException(status_code=401, detail="Kata sandi saat ini salah")
        password_hash = hash_password(request.new_password)
    updated = database.update_user(
        user.id,
        display_name=request.display_name,
        password_hash=password_hash,
    )
    return {"user": _public_user(updated), "message": "Pengaturan akun berhasil diperbarui"}


@app.get("/api/sessions")
def list_chat_sessions(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return {"sessions": database.list_sessions(user.id)}


@app.post("/api/sessions", status_code=201)
def create_chat_session(
    request: SessionCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    return database.create_session(user.id, request.title)


@app.get("/api/sessions/{session_id}/messages")
def list_chat_messages(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        rows = database.list_messages(session_id, user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    messages = []
    for row in rows:
        try:
            metadata = json.loads(row.pop("metadata_json", "{}"))
        except json.JSONDecodeError:
            metadata = {}
        messages.append({**row, "metadata": metadata})
    return {"messages": messages}


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_chat_session(
    session_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    if not database.delete_session(session_id, user.id):
        raise HTTPException(status_code=404, detail="Sesi percakapan tidak ditemukan")


@app.get("/api/chat/suggestions")
def chat_suggestions() -> dict[str, list[dict[str, str]]]:
    return {"suggestions": get_bot_suggestions()}


@app.get("/api/chat/model-status")
def chat_model_status() -> dict[str, Any]:
    return get_chatbot_pipeline().status()


@app.get("/api/documents")
def list_documents() -> dict[str, Any]:
    pipeline = get_chatbot_pipeline()
    return {
        "documents": pipeline.list_documents(),
        "status": pipeline.status(),
    }


@app.get("/api/documents/download/{file_name}")
def download_document(file_name: str) -> FileResponse:
    safe_name = Path(file_name).name
    if safe_name != file_name:
        raise HTTPException(status_code=400, detail="Nama file tidak valid")
    document_path = settings.raw_pdfs_dir / safe_name
    if not document_path.is_file() or document_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    return FileResponse(
        path=document_path,
        media_type="application/pdf",
        filename=safe_name,
        content_disposition_type="attachment",
    )


@app.get("/api/debug/runtime")
def debug_runtime(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    if not settings.debug_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Endpoint debug dinonaktifkan")
    require_admin(user)
    pipeline = get_chatbot_pipeline()
    llm_model = settings.gemini_model if settings.llm_provider == "gemini" else settings.ollama_model
    if settings.llm_provider == "auto":
        llm_model = f"auto: {settings.gemini_model} -> deterministic extractive fallback"

    return {
        "pid": os.getpid(),
        "app_file": __file__,
        "cwd": os.getcwd(),
        "settings": {
            "raw_pdfs_dir": str(settings.raw_pdfs_dir),
            "processed_chunks_path": str(settings.processed_chunks_path),
            "embeddings_path": str(settings.embeddings_path),
            "llm_provider": settings.llm_provider,
            "llm_model": llm_model,
            "gemini_key_present": bool(settings.gemini_api_key),
        },
        "rag_status": pipeline.status(),
        "documents": pipeline.list_documents(),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    http_request: Request,
    user: AuthenticatedUser | None = Depends(get_optional_user),
) -> ChatResponse:
    question = request.prompt
    if not question:
        raise HTTPException(status_code=422, detail="question atau message wajib diisi")
    _request_limiter.claim(
        "chat:global",
        settings.global_chat_rate_per_minute,
        60,
        "Layanan sedang menerima terlalu banyak pertanyaan. Coba lagi sebentar.",
    )
    requester = _authorization_key(http_request) if user is not None else _client_key(http_request)
    _request_limiter.claim(
        f"chat:{'user' if user else 'guest'}:{requester}",
        settings.user_chat_rate_per_minute if user else settings.guest_chat_rate_per_minute,
        60,
        "Batas pertanyaan per menit telah tercapai. Silakan tunggu sebentar.",
    )
    if user is None:
        if request.session_id:
            raise HTTPException(status_code=400, detail="Sesi tersimpan hanya tersedia setelah login")
        response = get_chatbot_pipeline().answer(question, history=request.history[-6:])
        response.session_id = None
        return response
    database.purge_expired(user_id=user.id)
    session = None
    if request.session_id:
        session = database.get_session(request.session_id, user.id)
        if not session:
            raise HTTPException(status_code=404, detail="Sesi percakapan tidak ditemukan atau sudah kedaluwarsa")
    else:
        session = database.create_session(user.id)

    stored_rows = database.list_messages(session["id"], user.id)
    stored_history = [
        ChatMessage(role=row["role"], text=row["content"])
        for row in stored_rows[-6:]
        if row["role"] in {"user", "bot"}
    ]
    history = request.history if not stored_history else stored_history
    response = get_chatbot_pipeline().answer(question, history=history)
    response.session_id = session["id"]
    database.add_message(session["id"], user.id, "user", question)
    metadata = response.model_dump(exclude={"answer", "reply", "session_id"}, mode="json")
    database.add_message(
        session["id"],
        user.id,
        "bot",
        response.answer,
        json.dumps(metadata, ensure_ascii=False),
    )
    return response


def _feedback_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded_for:
            try:
                return str(ip_address(forwarded_for))
            except ValueError:
                logger.warning("Ignoring invalid X-Forwarded-For address for feedback rate limiting.")
    return request.client.host if request.client else "unknown"


def _claim_feedback_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    window = settings.feedback_rate_limit_seconds
    with _feedback_rate_limit_lock:
        expired_before = now - window
        expired_ips = [ip for ip, timestamp in _feedback_attempts.items() if timestamp <= expired_before]
        for ip in expired_ips:
            del _feedback_attempts[ip]

        previous_attempt = _feedback_attempts.get(client_ip)
        if previous_attempt is not None:
            retry_after = max(1, int(window - (now - previous_attempt)))
            raise HTTPException(
                status_code=429,
                detail=f"Feedback dari koneksi ini sudah dikirim. Coba lagi dalam {retry_after} detik.",
                headers={"Retry-After": str(retry_after)},
            )
        _feedback_attempts[client_ip] = now


@app.post("/api/feedback", response_model=FeedbackResponse)
def submit_feedback(http_request: Request, request: FeedbackRequest) -> FeedbackResponse:
    feedback_dir = settings.backend_root / "data" / "feedback"
    feedback_path = feedback_dir / "feedback.jsonl"
    record = {
        "id": str(uuid4()),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "identity": (request.identity or "").strip() or None,
        "email": (request.email or "").strip() or None,
        "feedback": request.feedback.strip(),
    }
    if len(record["feedback"]) < 3:
        raise HTTPException(status_code=422, detail="Isi feedback wajib diisi")

    if not settings.smtp_username or not settings.smtp_password or not settings.smtp_from_email:
        logger.error("Feedback email is not configured. Set SMTP_USERNAME and SMTP_PASSWORD.")
        raise HTTPException(status_code=503, detail="Pengiriman email feedback belum dikonfigurasi")

    _claim_feedback_rate_limit(_feedback_client_ip(http_request))

    message = EmailMessage()
    message["Subject"] = settings.feedback_subject
    message["From"] = settings.smtp_from_email
    message["To"] = settings.feedback_recipient
    if record["email"]:
        message["Reply-To"] = record["email"]
    message.set_content(
        "Feedback Muallaf Bot\n\n"
        f"Waktu (UTC): {record['submitted_at']}\n"
        f"Identitas: {record['identity'] or '-'}\n"
        f"Email pengguna: {record['email'] or '-'}\n\n"
        "Isi feedback:\n"
        f"{record['feedback']}\n"
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("Failed to email chatbot feedback.", exc_info=True)
        raise HTTPException(status_code=502, detail="Feedback belum dapat dikirim melalui email") from exc

    try:
        feedback_dir.mkdir(parents=True, exist_ok=True)
        with feedback_path.open("a", encoding="utf-8") as feedback_file:
            feedback_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning("Feedback email was sent, but the local backup could not be stored.", exc_info=True)

    return FeedbackResponse(status="ok", message="Terima kasih. Feedback Anda telah dikirim melalui email.")
