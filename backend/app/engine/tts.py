"""
tts.py — Kokoro TTS synthesis module.

Architecture:
- One global KPipeline per lang_code, lazily initialized and cached.
- synthesize_node() generates WAV at 24kHz and caches to disk by node_id.
- If the file already exists it is reused (idempotent — safe for repeated calls).
- Audio dir defaults to /audio (Docker volume) or ./data/audio locally.
- All synthesis runs in a thread pool so it never blocks the asyncio event loop.
"""

import asyncio
import logging
import os
import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from kokoro import KPipeline

logger = logging.getLogger(__name__)

# ── Audio storage path ───────────────────────────────────────────────────────

AUDIO_DIR = Path("/audio") if os.path.exists("/.dockerenv") else Path("./data/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

TTS_SAMPLE_RATE = 24_000  # Kokoro outputs 24 kHz

# ── Pipeline cache (one per lang_code) ────────────────────────────────────────

_pipelines: dict[str, KPipeline] = {}


def _get_pipeline(lang_code: str) -> KPipeline:
    """Return a cached KPipeline for the given language code, creating it if needed."""
    if lang_code not in _pipelines:
        logger.info(f"Loading Kokoro pipeline for lang_code='{lang_code}'")
        _pipelines[lang_code] = KPipeline(lang_code=lang_code)
        logger.info(f"Kokoro pipeline for '{lang_code}' ready")
    return _pipelines[lang_code]


# ── Voice → lang_code mapping ─────────────────────────────────────────────────

# Voice prefix determines the language pipeline to load.
# a = American English, b = British English, etc.
_VOICE_PREFIX_TO_LANG = {
    "af": "a",  # American female
    "am": "a",  # American male
    "bf": "b",  # British female
    "bm": "b",  # British male
    "jf": "j",  # Japanese female
    "jm": "j",  # Japanese male
    "zf": "z",  # Mandarin female
    "zm": "z",  # Mandarin male
    "ef": "e",  # Spanish female
    "em": "e",  # Spanish male
    "ff": "f",  # French female
}

def _lang_code_for_voice(voice: str) -> str:
    prefix = voice[:2]
    return _VOICE_PREFIX_TO_LANG.get(prefix, "a")  # Default to American English


# ── Core synthesis ────────────────────────────────────────────────────────────

def _synthesize_blocking(text: str, voice: str, output_path: Path) -> None:
    """Blocking synthesis — runs in a thread executor, NOT the event loop."""
    lang_code = _lang_code_for_voice(voice)
    pipeline = _get_pipeline(lang_code)

    chunks = []
    for _, _, audio in pipeline(text, voice=voice, speed=1.0):
        chunks.append(audio)

    if not chunks:
        raise RuntimeError(f"Kokoro returned no audio for voice={voice!r}, text={text[:60]!r}")

    combined = np.concatenate(chunks)
    sf.write(str(output_path), combined, TTS_SAMPLE_RATE)
    logger.info(f"TTS synthesized {len(combined)/TTS_SAMPLE_RATE:.1f}s → {output_path}")


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
