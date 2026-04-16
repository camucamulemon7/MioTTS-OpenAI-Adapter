FROM docker.io/vllm/vllm-openai:latest

USER root

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG NLTK_DATA_BASE_URL
ARG NLTK_DATA_INSECURE_SSL

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
    NLTK_DATA_BASE_URL=${NLTK_DATA_BASE_URL} \
    NLTK_DATA_INSECURE_SSL=${NLTK_DATA_INSECURE_SSL} \
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
    NLTK_DATA=/usr/local/share/nltk_data \
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
import shlex
import subprocess
import tempfile
import zipfile
from pathlib import Path

nltk_data_dir = Path("/usr/local/share/nltk_data")
nltk_data_dir.mkdir(parents=True, exist_ok=True)

packages = {
    "tokenizers/punkt.zip": "tokenizers",
    "tokenizers/punkt_tab.zip": "tokenizers",
    "taggers/averaged_perceptron_tagger.zip": "taggers",
    "corpora/cmudict.zip": "corpora",
}

base_url = (
    os.environ.get("NLTK_DATA_BASE_URL")
    or "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages"
).rstrip("/")
proxy = (
    os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or os.environ.get("HTTP_PROXY")
    or os.environ.get("http_proxy")
)
insecure_ssl = os.environ.get("NLTK_DATA_INSECURE_SSL", "").lower() in {"1", "true", "yes"}

for relative_path, subdir in packages.items():
    url = f"{base_url}/{relative_path}"
    target_dir = nltk_data_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    cmd = ["curl", "-fL", "--retry", "3", "--retry-all-errors", "-o", str(tmp_path), url]
    if proxy:
        cmd.extend(["--proxy", proxy])
    if insecure_ssl:
        cmd.append("--insecure")

    print("Downloading", url)
    print("Command:", " ".join(shlex.quote(part) for part in cmd))
    try:
        subprocess.run(cmd, check=True)
        with zipfile.ZipFile(tmp_path) as zf:
            zf.extractall(target_dir)
    except Exception as exc:
        print(f"Failed while preparing {url}: {exc}", flush=True)
        raise
    finally:
        tmp_path.unlink(missing_ok=True)
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
