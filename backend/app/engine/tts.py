"""
tts.py — Kokoro TTS synthesis module (ONNX-optimized).

Architecture:
- Single global Kokoro instance (ONNX runtime, no PyTorch).
- synthesize_node() generates WAV at 24kHz and caches to disk by node_id.
- If the file already exists it is reused (idempotent — safe for repeated calls).
- Audio dir defaults to /audio (Docker volume) or ./data/audio locally.
- All synthesis runs in a thread pool so it never blocks the asyncio event loop.
- Model files (kokoro-v1.0-int8.onnx + voices-v1.0.bin) are downloaded at
  Docker build time and baked into the image layer.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import soundfile as sf

logger = logging.getLogger(__name__)

# ── Audio storage path ───────────────────────────────────────────────────────
# In Docker: /audio (shared volume).
# Locally: resolve to <project_root>/data/audio so TTS files land in the same
#   directory that FreeSWITCH's Docker volume maps (./data/audio:/audio).
#   __file__ = backend/app/engine/tts.py → .parent x3 = backend/ → .parent = project root

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_DIR = Path("/audio") if os.path.exists("/.dockerenv") else (_PROJECT_ROOT / "data" / "audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ── Model paths (baked into Docker image at /app/) ────────────────────────────

from pathlib import Path

# Base model paths dynamically resolved (works in Docker /app and local Windows)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = os.environ.get("KOKORO_MODEL_PATH", str(BASE_DIR / "kokoro-v1.0.onnx"))
VOICES_PATH = os.environ.get("KOKORO_VOICES_PATH", str(BASE_DIR / "voices-v1.0.bin"))

# ── Lazy singleton ────────────────────────────────────────────────────────────

_kokoro_instance = None


def _get_kokoro():
    """Return the cached Kokoro ONNX instance, creating it on first call."""
    global _kokoro_instance
    if _kokoro_instance is None:
        from kokoro_onnx import Kokoro
        logger.info(f"Loading Kokoro ONNX model from {MODEL_PATH}")
        _kokoro_instance = Kokoro(MODEL_PATH, VOICES_PATH)
        logger.info("Kokoro ONNX model ready")
    return _kokoro_instance


# ── Core synthesis ────────────────────────────────────────────────────────────

def _synthesize_blocking(text: str, voice: str, output_path: Path) -> None:
    """Blocking synthesis — runs in a thread executor, NOT the event loop."""
    kokoro = _get_kokoro()

    samples, sample_rate = kokoro.create(text, voice=voice, speed=1.0)

    if samples is None or len(samples) == 0:
        raise RuntimeError(f"Kokoro returned no audio for voice={voice!r}, text={text[:60]!r}")

    sf.write(str(output_path), samples, sample_rate)
    logger.info(f"TTS synthesized {len(samples)/sample_rate:.1f}s → {output_path}")


async def synthesize_node_prompt(
    node_id: str,
    text: str,
    voice: str = "af_heart",
    force: bool = False,
) -> str:
    """
    Synthesize TTS for an IVR node prompt.

    Returns the absolute path to the WAV file, suitable for passing to
    FreeSWITCH play_and_get_digits.

    Parameters
    ----------
    node_id : str
        UUID of the IvrNode — used as the cache key filename.
    text : str
        Text to synthesize.
    voice : str
        Kokoro voice code, e.g. 'af_heart', 'am_adam', 'bf_emma'.
    force : bool
        If True, re-synthesize even if the cached file already exists.
    """
    if not text or not text.strip():
        raise ValueError("Cannot synthesize empty TTS text")

    output_path = AUDIO_DIR / f"tts_{node_id}.wav"

    if output_path.exists() and not force:
        logger.debug(f"TTS cache hit for node {node_id} → {output_path}")
        return str(output_path)

    logger.info(f"Synthesizing TTS for node {node_id} voice={voice}")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,  # default thread pool
        _synthesize_blocking,
        text,
        voice,
        output_path,
    )

    return str(output_path)


async def invalidate_node_cache(node_id: str) -> None:
    """Delete the cached TTS WAV for a node (call when node text changes)."""
    path = AUDIO_DIR / f"tts_{node_id}.wav"
    if path.exists():
        path.unlink()
        logger.info(f"Invalidated TTS cache for node {node_id}")
