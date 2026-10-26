"""Modal deployment entrypoint for the IMC-MASK Muallaf Bot.

Run the one-off knowledge-base build before deploying the web endpoint:

    modal run deploy/modal_app.py::build_knowledge_base
    modal deploy deploy/modal_app.py
"""

from pathlib import Path
import json
import os
import subprocess
import sys
import time

import modal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

app = modal.App("muallaf-bot")
runtime_secret = modal.Secret.from_name("muallaf-bot-secrets")
generated_secret = modal.Secret.from_name("muallaf-bot-generated")
gemini_secret = modal.Secret.from_name("muallaf-bot-gemini")
groq_secret = modal.Secret.from_name("muallaf-bot-groq")

# Install CPU-only PyTorch first so sentence-transformers does not pull a much
# larger accelerator runtime. The model is cached while the image is built,
# which keeps cold starts independent of Hugging Face availability.
runtime_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgomp1")
    .run_commands(
        "pip install --index-url https://download.pytorch.org/whl/cpu "
        "--extra-index-url https://pypi.org/simple torch"
    )
    .pip_install_from_requirements(str(BACKEND_ROOT / "requirements-cloudrun.txt"))
    .env({"HF_HOME": "/opt/huggingface"})
    .run_commands(
        "python -c \"from sentence_transformers import SentenceTransformer; "
        f"SentenceTransformer('{EMBEDDING_MODEL}')\""
    )
    .env(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "APP_ENV": "production",
            "VECTOR_DB_TYPE": "pgvector",
            "RAG_ENGINE": "langchain",
            "LLM_PROVIDER": "auto",
            "GROQ_MODEL": "openai/gpt-oss-120b",
            # Keep this aligned with backend/app/config.py and .env.example.
            # The former 2.5 model is no longer available for this API account.
            "GEMINI_MODEL": "gemini-3.5-flash-lite",
            "CHAT_RETENTION_DAYS": "30",
            "ALLOW_REGISTRATION": "true",
            "DEBUG_ENDPOINT_ENABLED": "false",
            "TRUST_PROXY_HEADERS": "true",
            "EMBEDDING_BATCH_SIZE": "8",
            "FRONTEND_ORIGIN": "https://muallaf-bot.mwildankamil.workers.dev",
            "CORS_ORIGINS": "https://muallaf-bot.mwildankamil.workers.dev",
        }
    )
    .add_local_dir(
        str(BACKEND_ROOT / "app"),
        remote_path="/app/app",
        copy=True,
    )
    .add_local_dir(
        str(BACKEND_ROOT / "scripts"),
        remote_path="/app/scripts",
        copy=True,
    )
    .add_local_dir(
        str(BACKEND_ROOT / "data" / "raw_pdfs"),
        remote_path="/app/data/raw_pdfs",
        copy=True,
    )
)


@app.function(
    image=runtime_image,
    secrets=[runtime_secret, generated_secret, groq_secret, gemini_secret],
    cpu=2,
    memory=4096,
    timeout=1800,
    max_containers=1,
)
def build_knowledge_base() -> None:
    """Build embeddings atomically and persist them to Neon pgvector."""
    subprocess.run(
        ["python", "/app/scripts/build_knowledge_base.py"],
        cwd="/app",
        check=True,
    )


@app.function(
    image=runtime_image,
    secrets=[runtime_secret, generated_secret, groq_secret, gemini_secret],
    cpu=1,
    memory=3072,
    timeout=120,
    startup_timeout=300,
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
)
@modal.concurrent(max_inputs=2)
@modal.asgi_app(requires_proxy_auth=True)
def api():
    """Expose the existing FastAPI application as a Modal web endpoint."""
    sys.path.insert(0, "/app")
    from app.main import app as fastapi_app

    return fastapi_app


@app.function(
    image=runtime_image,
    secrets=[runtime_secret, generated_secret, groq_secret, gemini_secret],
    cpu=1,
    memory=3072,
    timeout=900,
    max_containers=1,
)
def run_groq_smoke(limit: int = 20) -> list[dict]:
    """Run the fixed 20-question pre-evaluation set using Groq only."""
    os.environ["LLM_PROVIDER"] = "groq"
    sys.path.insert(0, "/app")
    from app.config import get_settings
    from app.pipeline_factory import get_chatbot_pipeline

    get_settings.cache_clear()
    get_chatbot_pipeline.cache_clear()
    pipeline = get_chatbot_pipeline()
    questions = [
        "Saya baru belajar Islam, sebenarnya inti ajaran Islam itu apa?",
        "Kalau orang baru masuk Islam, hal pertama yang perlu dipahami tentang Allah apa ya?",
        "Apa saja rukun iman yang perlu diketahui oleh seorang mualaf?",
        "Rukun Islam dan rukun iman itu bedanya di mana?",
        "Apa makna dua kalimat syahadat bagi seorang Muslim?",
        "Setelah membaca syahadat, apa yang berubah dari diri seseorang?",
        "Saya masih sulit memahami konsep Tuhan dalam Islam. Bisa dijelaskan sederhana?",
        "Mengapa seorang Muslim hanya menyembah Allah?",
        "Apa maksudnya percaya kepada malaikat?",
        "Kenapa seorang Muslim perlu percaya kepada kitab-kitab Allah?",
        "Apa peran Nabi Muhammad bagi umat Islam?",
        "Hari akhir itu maksudnya apa dan kenapa harus diyakini?",
        "Saya belum paham qada dan qadar, bisa dijelaskan dengan bahasa ringan?",
        "Bagaimana adab seorang mualaf dalam mempelajari agama Islam?",
        "Apa saja contoh akhlak terpuji yang perlu dibiasakan dalam kehidupan sehari-hari?",
        "Bagaimana Islam mengajarkan sikap kepada orang lain yang berbeda agama?",
        "Saya belum bisa membaca Al-Qur'an, apakah itu masalah besar bagi mualaf?",
        "Apa yang sebaiknya saya pelajari dulu dari Al-Qur'an sebagai pemula?",
        "Bagaimana cara menjaga iman setelah masuk Islam?",
        "Kalau iman saya kadang naik turun, apa itu wajar bagi mualaf baru?",
    ]
    selected_questions = questions[: max(1, min(limit, len(questions)))]
    rows = []
    for number, question in enumerate(selected_questions, start=1):
        response = None
        for attempt in range(1, 4):
            candidate = pipeline.answer(question).model_dump(mode="json")
            # A Groq-only smoke test must not silently count the controlled
            # extractive fallback as a successful generative answer.
            if str(candidate.get("mode", "")).startswith("rag"):
                response = candidate
                break
            if attempt < 3:
                time.sleep(30 * attempt)
        if response is None:
            rows.append(
                {
                    "no": number,
                    "question": question,
                    "status": "failed_no_generative_answer",
                    "answer": candidate.get("answer", ""),
                    "mode": candidate.get("mode"),
                    "sources": candidate.get("sources") or [],
                    "retrieval_confidence": candidate.get("retrieval_confidence"),
                    "model_status": candidate.get("model_status"),
                    "attempts": 3,
                }
            )
            break
        rows.append(
            {
                "no": number,
                "question": question,
                "status": "passed_generative",
                "answer": response.get("answer", ""),
                "mode": response.get("mode"),
                "sources": response.get("sources") or [],
                "retrieved_contexts": [
                    result.chunk.content
                    for result in pipeline._retrieve_results(question, pipeline.settings.top_k)
                    if result.chunk.content
                ],
                "retrieval_confidence": response.get("retrieval_confidence"),
                "model_status": response.get("model_status"),
                "attempts": attempt,
            }
        )
        # The free Groq project currently allows 8,000 tokens/minute for this
        # model. At roughly 1,800 input tokens/request, a 20-second interval
        # keeps the smoke run below that limit with useful safety margin.
        if number < len(selected_questions):
            time.sleep(20)
    return rows


@app.function(
    image=runtime_image,
    secrets=[runtime_secret, generated_secret, groq_secret, gemini_secret],
    cpu=1,
    memory=3072,
    timeout=300,
    max_containers=1,
)
def compare_answer_providers(question: str) -> list[dict]:
    """Compare generators against the same question and retrieval pipeline."""
    sys.path.insert(0, "/app")
    from app.config import get_settings
    from app.pipeline_factory import get_chatbot_pipeline

    rows = []
    for provider in ("groq", "gemini", "extractive"):
        os.environ["LLM_PROVIDER"] = "ollama" if provider == "extractive" else provider
        if provider == "extractive":
            os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"
        get_settings.cache_clear()
        get_chatbot_pipeline.cache_clear()
        pipeline = get_chatbot_pipeline()
        started = time.monotonic()
        response = pipeline.answer(question).model_dump(mode="json")
        rows.append(
            {
                "provider": provider,
                "answer": response.get("answer", ""),
                "mode": response.get("mode"),
                "sources": response.get("sources") or [],
                "retrieval_confidence": response.get("retrieval_confidence"),
                "model_status": response.get("model_status"),
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
        )
    return rows


@app.local_entrypoint()
def groq_smoke(limit: int = 20, output_path: str = ""):
    payload = run_groq_smoke.remote(limit)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
        print(f"Saved Groq smoke results to {destination}")
    print(rendered)


@app.local_entrypoint()
def compare_providers(
    question: str = "Apa saja rukun iman yang perlu diketahui oleh seorang mualaf?",
):
    print(json.dumps(compare_answer_providers.remote(question), ensure_ascii=False, indent=2))
