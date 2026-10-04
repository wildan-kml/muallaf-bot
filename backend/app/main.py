import os
import logging
import json
import smtplib
import threading
import time
from ipaddress import ip_address
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .pipeline_factory import get_chatbot_pipeline
from .schemas import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
)


settings = get_settings()
logger = logging.getLogger(__name__)
_feedback_attempts: dict[str, float] = {}
_feedback_rate_limit_lock = threading.Lock()

for directory in (settings.raw_pdfs_dir, settings.processed_dir, settings.vector_db_dir):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="IMC-MASK API",
    version="0.2.0",
    description="API IMC-MASK untuk chatbot Muallaf Bot berbasis RAG.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
def debug_runtime() -> dict[str, Any]:
    pipeline = get_chatbot_pipeline()
    llm_model = settings.gemini_model if settings.llm_provider == "gemini" else settings.ollama_model
    if settings.llm_provider == "auto":
        llm_model = f"auto: {settings.gemini_model} -> {settings.ollama_model}"

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
def chat(request: ChatRequest) -> ChatResponse:
    question = request.prompt
    if not question:
        raise HTTPException(status_code=422, detail="question atau message wajib diisi")

    return get_chatbot_pipeline().answer(question, history=request.history)


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
