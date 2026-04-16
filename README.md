# MioTTS-OpenAI-Adapter

Run [`Aratako/MioTTS-Inference`](https://github.com/Aratako/MioTTS-Inference) and expose an OpenAI-compatible Text-to-Speech API for tools such as OpenWebUI.

This project starts three processes inside one container:

- `vLLM` serving a MioTTS-compatible model
- `MioTTS-Inference` REST API
- an OpenAI-compatible adapter exposing `/v1/audio/speech`

## What This Project Does

`MioTTS-Inference` does not expose an OpenAI-compatible TTS API out of the box. This repository adds a thin compatibility layer so OpenAI-style clients can call:

- `POST /v1/audio/speech`
- `GET /v1/models`
- `GET /health`

The adapter also supports:

- OpenAI-style `voice`
- `response_format`
- `output_format`
- `speed`

## Requirements

- Docker
- NVIDIA GPU support for Docker
- enough VRAM for the model you plan to run
- a Hugging Face token if the model requires gated access

## Quick Start

### 1. Build the image

```bash
cd MioTTS-openai
docker build -t miotts-openai-adapter:latest .
```

If you build behind an HTTP/HTTPS proxy, pass the proxy environment variables to `docker build`, for example:

```bash
docker build \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  -t miotts-openai-adapter:latest .
```

### 2. Run the container

```bash
mkdir -p ./huggingface ./presets

docker run -d \
  --name vllm-miotts \
  --gpus all \
  --restart unless-stopped \
  -p 8005:8080 \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -e MIOTTS_MODEL="your-model-id" \
  -v "$PWD/huggingface:/home/app/.cache/huggingface" \
  -v "$PWD/presets:/opt/MioTTS-Inference/presets" \
  miotts-openai-adapter:latest
```

You can add optional environment variables such as:

```bash
-e VLLM_GPU_MEMORY_UTILIZATION="0.50" \
-e VLLM_MAX_MODEL_LEN="1024" \
-e VLLM_TENSOR_PARALLEL_SIZE="1" \
-e OPENAI_TTS_MODEL_NAME="miotts" \
-e OPENAI_TTS_DEFAULT_VOICE="default" \
-e OPENAI_TTS_DEFAULT_RESPONSE_FORMAT="mp3"
```

If you prefer a helper script for your local environment:

```bash
cd MioTTS-openai
chmod +x run.sh
./run.sh
```

## OpenWebUI Configuration

Use the OpenAI TTS engine and point it to this adapter:

```env
AUDIO_TTS_ENGINE=openai
AUDIO_TTS_OPENAI_API_BASE_URL=http://host.docker.internal:8005/v1
AUDIO_TTS_OPENAI_API_KEY=dummy
AUDIO_TTS_MODEL=miotts
AUDIO_TTS_VOICE=default
```

You can also pass additional OpenAI-style parameters from OpenWebUI, for example:

```json
{"speed": 1.2}
```

## Custom Presets

Preset availability and naming depend on the upstream `MioTTS-Inference` setup. For the latest built-in presets and reference behavior, check the upstream project documentation.

The bundled presets may not be suitable for commercial use. For production or commercial deployments, generate your own presets from audio you are legally allowed to use.

`MioTTS-Inference` includes a preset generator:

```bash
python3 /opt/MioTTS-Inference/scripts/generate_preset.py \
  --audio /path/to/reference.wav \
  --preset-id myvoice \
  --output-dir /opt/MioTTS-Inference/presets
```

This project automatically seeds the default preset directory on startup if the mounted `presets/` directory is empty.

## API Example

```bash
curl -X POST http://localhost:8005/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "miotts",
    "input": "Hello from MioTTS.",
    "voice": "default",
    "response_format": "mp3",
    "speed": 1.0
  }' \
  --output sample.mp3
```

## Notes

- `speed` is applied as a post-processing tempo adjustment in the adapter.
- The adapter keeps generated audio in memory and returns it directly in the HTTP response.
- Model and cache files are stored under the mounted Hugging Face cache directory.
- If you see a warning about FlashAttention not being installed, the stack can still work, but performance may be lower.
- Model selection, presets, and quality characteristics ultimately depend on the upstream `MioTTS-Inference` stack and the model you choose.

## Repository Layout

- `Dockerfile`: container build definition
- `entrypoint.sh`: startup orchestration for all three services
- `openai_tts_adapter.py`: OpenAI-compatible TTS adapter
- `run.sh`: convenience launcher

## License and Upstream

Please review the licenses and usage terms of:

- `MioTTS-Inference`
- `MioTTS` models
- `MioCodec`
- any presets or reference audio you use

This repository is an adapter layer and does not change the original licensing terms of upstream models or voice assets.
