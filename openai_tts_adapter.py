import argparse
import base64
import json
import math
import os
import subprocess
from functools import lru_cache
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


UPSTREAM_BASE_URL = os.getenv("OPENAI_TTS_UPSTREAM_BASE_URL", "http://127.0.0.1:8001")
MODEL_NAME = os.getenv("OPENAI_TTS_MODEL_NAME", "miotts-1.7b")
DEFAULT_VOICE = os.getenv("OPENAI_TTS_DEFAULT_VOICE", "jp_female")
DEFAULT_RESPONSE_FORMAT = os.getenv("OPENAI_TTS_DEFAULT_RESPONSE_FORMAT", "mp3")
REQUEST_TIMEOUT = float(os.getenv("OPENAI_TTS_TIMEOUT", "300"))

DEFAULT_VOICE_MAP = {
    "alloy": "jp_female",
    "ash": "jp_male",
    "echo": "en_male",
    "fable": "en_female",
    "nova": "jp_female",
    "onyx": "jp_male",
    "sage": "en_female",
    "shimmer": "jp_female",
}

CONTENT_TYPES = {
    "aac": "audio/aac",
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "wav": "audio/wav",
}

FFMPEG_FORMATS = {"aac", "flac", "mp3", "opus", "wav"}

app = FastAPI(title="MioTTS OpenAI-Compatible Adapter", version="1.0.0")


class SpeechRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    model: str = Field(default=MODEL_NAME)
    input: str
    voice: str | None = None
    response_format: str | None = None
    output_format: str | None = Field(default=None, alias="output_format")
    speed: float | None = None


@lru_cache(maxsize=1)
def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT)


def _voice_map() -> dict[str, str]:
    raw = os.getenv("OPENAI_TTS_VOICE_PRESET_MAP", "")
    if not raw:
      return DEFAULT_VOICE_MAP

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OPENAI_TTS_VOICE_PRESET_MAP must be valid JSON") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("OPENAI_TTS_VOICE_PRESET_MAP must be a JSON object")

    normalized = {str(key): str(value) for key, value in parsed.items()}
    return {**DEFAULT_VOICE_MAP, **normalized}


def _resolve_preset(voice: str | None) -> str:
    requested = voice or DEFAULT_VOICE
    voice_map = _voice_map()
    return voice_map.get(requested, requested)


def _content_type(fmt: str) -> str:
    return CONTENT_TYPES.get(fmt, "application/octet-stream")


def _normalize_speed(speed: float | None) -> float:
    if speed is None:
        return 1.0
    if not math.isfinite(speed):
        raise HTTPException(status_code=400, detail="speed must be a finite number")
    if speed <= 0:
        raise HTTPException(status_code=400, detail="speed must be greater than 0")
    return speed


def _atempo_filters(speed: float) -> list[str]:
    if math.isclose(speed, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        return []

    filters: list[str] = []
    remaining = speed

    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0

    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5

    filters.append(f"atempo={remaining:.6f}")
    return filters


def _transcode(wav_bytes: bytes, target_format: str, speed: float) -> bytes:
    if target_format == "wav":
        if math.isclose(speed, 1.0, rel_tol=1e-6, abs_tol=1e-6):
            return wav_bytes

    if target_format not in FFMPEG_FORMATS:
        raise HTTPException(status_code=400, detail=f"Unsupported response_format: {target_format}")

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "wav",
        "-i",
        "pipe:0",
    ]

    filters = _atempo_filters(speed)
    if filters:
        cmd.extend(["-filter:a", ",".join(filters)])

    if target_format == "opus":
        cmd.extend(["-c:a", "libopus"])
    elif target_format == "aac":
        cmd.extend(["-c:a", "aac"])
    elif target_format == "mp3":
        cmd.extend(["-c:a", "libmp3lame"])

    cmd.extend(["-f", target_format, "pipe:1"])

    proc = subprocess.run(cmd, input=wav_bytes, capture_output=True, check=False)
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", errors="ignore").strip() or "ffmpeg transcoding failed"
        raise HTTPException(status_code=500, detail=message)

    return proc.stdout


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "created": 0,
                "owned_by": "local",
            }
        ],
        "object": "list",
    }


@app.post("/v1/audio/speech")
async def speech(request: SpeechRequest) -> Response:
    if not request.input.strip():
        raise HTTPException(status_code=400, detail="input must not be empty")

    target_format = (request.response_format or request.output_format or DEFAULT_RESPONSE_FORMAT).lower()
    preset_id = _resolve_preset(request.voice)
    speed = _normalize_speed(request.speed)

    payload = {
        "text": request.input,
        "reference": {
            "type": "preset",
            "preset_id": preset_id,
        },
        "output": {"format": "base64"},
    }

    try:
        response = await client().post(f"{UPSTREAM_BASE_URL}/v1/tts", json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    data = response.json()
    try:
        wav_bytes = base64.b64decode(data["audio"])
    except KeyError as exc:
        raise HTTPException(status_code=502, detail="Upstream response did not include audio") from exc

    audio_bytes = _transcode(wav_bytes, target_format, speed)
    headers = {
        "X-MioTTS-Preset": preset_id,
    }
    return Response(content=audio_bytes, media_type=_content_type(target_format), headers=headers)


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_: Any, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenAI-compatible adapter for MioTTS")
    parser.add_argument("--host", default=os.getenv("OPENAI_TTS_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OPENAI_TTS_PORT", "8080")))
    parser.add_argument("--log-level", default=os.getenv("OPENAI_TTS_LOG_LEVEL", "info"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
