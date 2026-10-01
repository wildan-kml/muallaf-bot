import os
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .pipeline_factory import get_chatbot_pipeline
from .schemas import (
    ChatRequest,
    ChatResponse,
)


settings = get_settings()
logger = logging.getLogger(__name__)

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
