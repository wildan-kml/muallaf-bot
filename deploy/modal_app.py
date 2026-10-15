"""Modal deployment entrypoint for the IMC-MASK Muallaf Bot.

Run the one-off knowledge-base build before deploying the web endpoint:

    modal run deploy/modal_app.py::build_knowledge_base
    modal deploy deploy/modal_app.py
"""

from pathlib import Path
import subprocess
import sys

import modal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"

app = modal.App("muallaf-bot")
runtime_secret = modal.Secret.from_name("muallaf-bot-secrets")
generated_secret = modal.Secret.from_name("muallaf-bot-generated")

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
            "GEMINI_MODEL": "gemini-2.5-flash",
            "CHAT_RETENTION_DAYS": "30",
            "ALLOW_REGISTRATION": "true",
            "DEBUG_ENDPOINT_ENABLED": "false",
            "TRUST_PROXY_HEADERS": "true",
            "EMBEDDING_BATCH_SIZE": "8",
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
    secrets=[runtime_secret, generated_secret],
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
    secrets=[runtime_secret, generated_secret],
    cpu=1,
    memory=3072,
    timeout=300,
    startup_timeout=300,
    min_containers=0,
    max_containers=1,
    scaledown_window=60,
)
@modal.concurrent(max_inputs=4)
@modal.asgi_app()
def api():
    """Expose the existing FastAPI application as a Modal web endpoint."""
    sys.path.insert(0, "/app")
    from app.main import app as fastapi_app

    return fastapi_app
