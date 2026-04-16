#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-vllm-miotts:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-vllm-miotts}"
HOST_PORT="${HOST_PORT:-8005}"
HF_CACHE_DIR="${HF_CACHE_DIR:-$PWD/huggingface}"
PRESETS_DIR="${PRESETS_DIR:-$PWD/presets}"

mkdir -p "${HF_CACHE_DIR}" "${PRESETS_DIR}"

docker build -t "${IMAGE_NAME}" .

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

docker run -d \
  --name "${CONTAINER_NAME}" \
  --gpus all \
  --restart unless-stopped \
  -p "${HOST_PORT}:8080" \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -e MIOTTS_MODEL=Aratako/MioTTS-0.6B \
  -e VLLM_GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.50}" \
  -e VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-1024}" \
  -e VLLM_TENSOR_PARALLEL_SIZE="${VLLM_TENSOR_PARALLEL_SIZE:-1}" \
  -e OPENAI_TTS_MODEL_NAME="${OPENAI_TTS_MODEL_NAME:-miotts-1.7b}" \
  -e OPENAI_TTS_DEFAULT_VOICE="${OPENAI_TTS_DEFAULT_VOICE:-jp_female}" \
  -e OPENAI_TTS_DEFAULT_RESPONSE_FORMAT="${OPENAI_TTS_DEFAULT_RESPONSE_FORMAT:-mp3}" \
  -e OPENAI_TTS_VOICE_PRESET_MAP_JSON="${OPENAI_TTS_VOICE_PRESET_MAP_JSON:-}" \
  -v "./references:/opt/MioTTS-Inference/references" \
  -v "${HF_CACHE_DIR}:/home/app/.cache/huggingface" \
  -v "${PRESETS_DIR}:/opt/MioTTS-Inference/presets" \
  "${IMAGE_NAME}"


# docker exec -it vllm-miotts python3 /opt/MioTTS-Inference/scripts/generate_preset.py \
#   --audio /opt/MioTTS-Inference/references/myvoice.wav \
#   --preset-id myvoice \
#   --output-dir /opt/MioTTS-Inference/presets
