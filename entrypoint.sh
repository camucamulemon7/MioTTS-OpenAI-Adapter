#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${HF_TOKEN:-}" && -z "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
fi

if [[ -n "${OPENAI_TTS_VOICE_PRESET_MAP_JSON:-}" ]]; then
  export OPENAI_TTS_VOICE_PRESET_MAP="${OPENAI_TTS_VOICE_PRESET_MAP_JSON}"
fi

seed_default_presets() {
  local presets_dir="${MIOTTS_REPO_DIR}/presets"
  local default_presets_dir="/opt/miotts-default-presets"

  mkdir -p "${presets_dir}"

  if find "${presets_dir}" -mindepth 1 -print -quit | grep -q .; then
    return 0
  fi

  echo "Preset directory is empty. Seeding bundled defaults into ${presets_dir}"
  cp -a "${default_presets_dir}/." "${presets_dir}/"
}

wait_for_http() {
  local url="$1"
  local name="$2"
  local attempts="${3:-240}"

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for ${name} at ${url}" >&2
  return 1
}

pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait || true
}

trap cleanup EXIT INT TERM

cd "${MIOTTS_REPO_DIR}"
seed_default_presets

vllm_host="${VLLM_HOST}"
vllm_port="${VLLM_PORT}"
vllm_max_model_len="${VLLM_MAX_MODEL_LEN}"
vllm_gpu_memory_utilization="${VLLM_GPU_MEMORY_UTILIZATION}"
vllm_tensor_parallel_size="${VLLM_TENSOR_PARALLEL_SIZE}"

# Prevent vLLM from treating our helper env vars as its own config env vars.
unset VLLM_HOST VLLM_PORT VLLM_MAX_MODEL_LEN VLLM_GPU_MEMORY_UTILIZATION VLLM_TENSOR_PARALLEL_SIZE

vllm_cmd=(
  vllm serve "${MIOTTS_MODEL}"
  --host "${vllm_host}"
  --port "${vllm_port}"
  --max-model-len "${vllm_max_model_len}"
  --gpu-memory-utilization "${vllm_gpu_memory_utilization}"
  --tensor-parallel-size "${vllm_tensor_parallel_size}"
)

if [[ -n "${VLLM_DTYPE:-}" ]]; then
  vllm_cmd+=(--dtype "${VLLM_DTYPE}")
fi

if [[ -n "${VLLM_EXTRA_ARGS:-}" ]]; then
  read -r -a extra_vllm_args <<<"${VLLM_EXTRA_ARGS}"
  vllm_cmd+=("${extra_vllm_args[@]}")
fi

echo "Starting vLLM for ${MIOTTS_MODEL}"
"${vllm_cmd[@]}" &
pids+=("$!")

wait_for_http "http://127.0.0.1:${vllm_port}/health" "vLLM"

miotts_cmd=(
  python3 run_server.py
  --host "${MIOTTS_HOST}"
  --port "${MIOTTS_PORT}"
  --llm-base-url "http://127.0.0.1:${vllm_port}/v1"
)

if [[ -n "${MIOTTS_EXTRA_ARGS:-}" ]]; then
  read -r -a extra_miotts_args <<<"${MIOTTS_EXTRA_ARGS}"
  miotts_cmd+=("${extra_miotts_args[@]}")
fi

echo "Starting MioTTS API"
"${miotts_cmd[@]}" &
pids+=("$!")

wait_for_http "http://127.0.0.1:${MIOTTS_PORT}/health" "MioTTS API"

adapter_cmd=(
  python3 /opt/openai_tts_adapter.py
  --host "${OPENAI_TTS_HOST}"
  --port "${OPENAI_TTS_PORT}"
)

echo "Starting OpenAI-compatible TTS adapter"
"${adapter_cmd[@]}" &
pids+=("$!")

wait -n "${pids[@]}"
