FROM docker.io/vllm/vllm-openai:latest

USER root

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${http_proxy} \
    https_proxy=${https_proxy} \
    no_proxy=${no_proxy} \
    APP_USER=app \
    APP_UID=1000 \
    APP_GID=1000 \
    APP_HOME=/home/app \
    MIOTTS_REPO_DIR=/opt/MioTTS-Inference \
    MIOTTS_MODEL=Aratako/MioTTS-1.7B \
    VLLM_HOST=0.0.0.0 \
    VLLM_PORT=8000 \
    VLLM_MAX_MODEL_LEN=1024 \
    VLLM_GPU_MEMORY_UTILIZATION=0.50 \
    VLLM_TENSOR_PARALLEL_SIZE=1 \
    MIOTTS_HOST=0.0.0.0 \
    MIOTTS_PORT=8002 \
    MIOTTS_DEVICE=cuda \
    OPENAI_TTS_HOST=0.0.0.0 \
    OPENAI_TTS_PORT=8080 \
    OPENAI_TTS_UPSTREAM_BASE_URL=http://127.0.0.1:8002 \
    OPENAI_TTS_MODEL_NAME=miotts-1.7b \
    OPENAI_TTS_DEFAULT_VOICE=jp_female \
    OPENAI_TTS_DEFAULT_RESPONSE_FORMAT=mp3 \
    HOME=/home/app \
    XDG_CACHE_HOME=/home/app/.cache \
    HF_HOME=/home/app/.cache/huggingface \
    HUGGING_FACE_HUB_CACHE=/home/app/.cache/huggingface \
    PATH=/usr/local/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    git \
    libmecab-dev \
    libsndfile1 \
    mecab \
    mecab-ipadic-utf8 \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${APP_GID}" "${APP_USER}" && \
    useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --home-dir "${APP_HOME}" --shell /bin/bash "${APP_USER}" && \
    mkdir -p "${APP_HOME}/.cache/huggingface"

RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

RUN git clone --depth 1 https://github.com/Aratako/MioTTS-Inference.git "${MIOTTS_REPO_DIR}"

RUN cp -a "${MIOTTS_REPO_DIR}/presets" /opt/miotts-default-presets

WORKDIR /opt/mio-openai-adapter

COPY pyproject.toml README.md openai_tts_adapter.py ./

RUN uv pip install --system \
    "pip" \
    "setuptools<81" \
    "wheel" && \
    uv pip install --system . && \
    python3 - <<'PY'
import os
import nltk

proxy = (
    os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or os.environ.get("HTTP_PROXY")
    or os.environ.get("http_proxy")
)

if proxy:
    nltk.set_proxy(proxy)

for package in ("punkt", "punkt_tab", "averaged_perceptron_tagger", "cmudict"):
    ok = nltk.download(package, quiet=True, raise_on_error=True)
    if not ok:
        raise RuntimeError(f"failed to download NLTK package: {package}")
PY

COPY entrypoint.sh /opt/entrypoint.sh
COPY openai_tts_adapter.py /opt/openai_tts_adapter.py

WORKDIR ${MIOTTS_REPO_DIR}

RUN chmod +x /opt/entrypoint.sh && \
    chown -R "${APP_UID}:${APP_GID}" "${APP_HOME}" "${MIOTTS_REPO_DIR}" /opt/miotts-default-presets /opt/mio-openai-adapter /opt/entrypoint.sh /opt/openai_tts_adapter.py

USER ${APP_UID}:${APP_GID}

EXPOSE 8000 8002 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${OPENAI_TTS_PORT}/health" || exit 1

ENTRYPOINT ["/opt/entrypoint.sh"]
