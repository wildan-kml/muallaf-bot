FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY requirements*.txt ./
ARG REQUIREMENTS_FILE=requirements-cloudrun.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install \
       --index-url https://download.pytorch.org/whl/cpu \
       --extra-index-url https://pypi.org/simple torch \
    && /opt/venv/bin/pip install -r "${REQUIREMENTS_FILE}"

# Cache the embedding model in the image. Cloud Run instances have an
# ephemeral filesystem and may be created from zero after being idle; baking
# the reviewed model into the image avoids a network download on every cold
# start.
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
ENV HF_HOME=/opt/huggingface
RUN /opt/venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

FROM python:3.12-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    HF_HOME=/opt/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN groupadd --system app && useradd --system --gid app --home /app app
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/huggingface /opt/huggingface
COPY . .
RUN chown -R app:app /app /opt/huggingface
USER app

EXPOSE 8080

CMD ["python", "-m", "app.server"]
