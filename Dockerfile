FROM docker.io/vllm/vllm-openai:latest

USER root

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
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
    OPENAI_TTS_DEFAULT_RESPONSE_FORMAT=mp3

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

RUN git clone --depth 1 https://github.com/Aratako/MioTTS-Inference.git "${MIOTTS_REPO_DIR}"

RUN cp -a "${MIOTTS_REPO_DIR}/presets" /opt/miotts-default-presets

WORKDIR ${MIOTTS_REPO_DIR}

RUN python3 -m pip install --upgrade pip "setuptools<81" wheel && \
    python3 -m pip install \
    "accelerate>=1.12.0" \
    "fastapi>=0.111.0" \
    "gradio>=4.0.0" \
    "httpx>=0.27.0" \
    "g2p_en" \
    "miocodec @ git+https://github.com/Aratako/MioCodec@main" \
    "nltk" \
    "orjson" \
    "pyopenjtalk" \
    "python-multipart>=0.0.9" \
    "soundfile" \
    "transformers<5" \
    "uvicorn>=0.30.0" \
    "ninja>=1.13.0" && \
    python3 -m nltk.downloader punkt punkt_tab averaged_perceptron_tagger cmudict

COPY entrypoint.sh /opt/entrypoint.sh
COPY openai_tts_adapter.py /opt/openai_tts_adapter.py

RUN chmod +x /opt/entrypoint.sh

EXPOSE 8000 8002 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${OPENAI_TTS_PORT}/health" || exit 1

ENTRYPOINT ["/opt/entrypoint.sh"]
