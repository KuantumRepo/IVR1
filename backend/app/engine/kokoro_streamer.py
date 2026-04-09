"""
kokoro_streamer.py — Streaming TTS via Kokoro ONNX.

Provides a generator that yields audio chunks for real-time streaming
to FreeSWITCH via uuid_broadcast / raw L16 PCM.
"""

import logging
import os
from kokoro_onnx import Kokoro

logger = logging.getLogger(__name__)

MODEL_PATH = os.environ.get("KOKORO_MODEL_PATH", "/app/kokoro-v1.0-int8.onnx")
VOICES_PATH = os.environ.get("KOKORO_VOICES_PATH", "/app/voices-v1.0.bin")

# Cache instance globally
_kokoro = None


def _get_kokoro():
    global _kokoro
    if _kokoro is None:
        logger.info("Initializing Kokoro ONNX for low-latency streaming")
        _kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
    return _kokoro


async def generate_tts_stream(text: str, voice: str = "af_heart"):
    """
    Generates TTS audio in a single shot via Kokoro ONNX.
    For true streaming, chunk the text and call create() per chunk.
    """
    kokoro = _get_kokoro()
    samples, sample_rate = kokoro.create(text, voice=voice, speed=1.0)
    yield samples
