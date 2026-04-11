"""
Whisper AMD WebSocket Server
═══════════════════════════════════════════════════════════════════════════════

Layer 2 of the 3-layer AMD system. This service:
  1. Loads faster-whisper (INT8, CPU) model ONCE at startup (~400MB RAM)
  2. Loads a TF-IDF + LogisticRegression text classifier at startup
  3. Accepts PCM16 16kHz mono audio over WebSocket
  4. After EARLY_SEC seconds of audio: emits an "early" decision
  5. On {"type":"flush"}: emits a "final" decision from the full buffer

Only ~30-40% of calls reach this service (smart routing from Lua).

Protocol:
  Client → Server:
    - Binary frames: raw PCM16 16kHz mono audio (20-40ms chunks)
    - JSON text frame: {"type":"flush"} to request final decision
    - JSON text frame: {"type":"close"} to end session cleanly
  Server → Client:
    - JSON text frame: {type, label, confidence, proba_human, transcript, elapsed_ms}

Based on architecture from github.com/rixwankhan/whisper-vm-finetune
"""

import asyncio
import io
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

from classifier import AMDClassifier

# ── Configuration (from environment) ──────────────────────────────────────────

# Whisper model size: "tiny", "base", "small", "medium", "large-v3"
# "small" with INT8 is the sweet spot for CPU AMD: fast enough for <2s latency,
# accurate enough for short greeting transcription.
MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")

# Device: "cpu" or "cuda" (we only support CPU in this deployment)
DEVICE = os.getenv("DEVICE", "cpu")

# Quantization: "int8" for CPU, "float16" for GPU
# INT8 via CTranslate2 gives ~3x speedup over float32 on CPU with minimal
# accuracy loss on short audio segments.
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")

# Seconds of audio to buffer before emitting an early decision.
# 2.0s captures most VM greeting openings ("Hi, you've reached...")
# while keeping latency under the 3.5s target.
EARLY_SEC = float(os.getenv("EARLY_SEC", "2.0"))

# Audio parameters — must match what Lua sends over the WebSocket
SAMPLE_RATE = 16000   # 16kHz
SAMPLE_WIDTH = 2      # PCM16 = 2 bytes per sample
CHANNELS = 1          # mono

# Classifier model path
CLASSIFIER_PATH = os.getenv(
    "CLASSIFIER_PATH",
    str(Path(__file__).parent / "models" / "text_cls.joblib")
)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("whisper-amd")

# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(title="Whisper AMD Sidecar", version="1.0.0")

# Global model references — loaded ONCE at startup, shared across all requests.
# This is critical: loading a Whisper model takes 5-15s; we cannot do it per-call.
whisper_model: WhisperModel | None = None
classifier: AMDClassifier | None = None


@app.on_event("startup")
async def load_models():
    """Load Whisper + classifier models once at process startup."""
    global whisper_model, classifier

    logger.info(f"Loading Whisper model: size={MODEL_SIZE}, device={DEVICE}, compute={COMPUTE_TYPE}")
    start = time.monotonic()
    whisper_model = WhisperModel(
        MODEL_SIZE,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        # Limit CPU threads to avoid contention at high concurrency.
        # 4 threads is optimal for INT8 on 4-core servers.
        cpu_threads=int(os.getenv("WHISPER_THREADS", "4")),
    )
    elapsed = time.monotonic() - start
    logger.info(f"Whisper model loaded in {elapsed:.1f}s")

    # Load text classifier (TF-IDF + LogReg)
    classifier = AMDClassifier(CLASSIFIER_PATH)
    logger.info("AMD text classifier loaded")


@app.get("/healthz")
async def healthz():
    """Health check — returns 200 only when both models are loaded."""
    if whisper_model is None:
        return {"status": "loading", "model": "whisper"}, 503
    if classifier is None or not classifier.ready:
        return {"status": "loading", "model": "classifier"}, 503
    return {"status": "ok", "model_size": MODEL_SIZE, "device": DEVICE}


def _transcribe(audio_np: np.ndarray) -> str:
    """
    Run Whisper inference on a numpy audio array.
    Returns the concatenated transcript text.

    Uses beam_size=1 for lowest latency (greedy decoding).
    VAD filter is disabled — we want to transcribe everything including
    silence patterns, which carry signal for the classifier.
    """
    segments, _ = whisper_model.transcribe(
        audio_np,
        language="en",
        beam_size=1,            # Greedy decode — fastest
        best_of=1,              # No sampling alternatives
        vad_filter=False,       # Don't skip silence — it's signal for AMD
        without_timestamps=True # We don't need word timestamps
    )
    # Concatenate all segment texts
    return " ".join(seg.text.strip() for seg in segments).strip()


def _classify(transcript: str) -> dict:
    """
    Classify a transcript as human or machine using the text classifier.
    Returns dict with label, confidence, proba_human.
    """
    if not transcript or not classifier or not classifier.ready:
        # No transcript = can't classify, return uncertain
        return {
            "label": "unknown",
            "confidence": 0.0,
            "proba_human": 0.5,
        }

    result = classifier.predict(transcript)
    return result


@app.websocket("/ws/amd")
async def amd_websocket(ws: WebSocket):
    """
    WebSocket endpoint for streaming AMD.

    Protocol:
      1. Client connects
      2. Client sends binary PCM16 16kHz mono frames (20-40ms each)
      3. After EARLY_SEC of audio accumulated → server sends early decision
      4. Client sends {"type":"flush"} → server sends final decision
      5. Client sends {"type":"close"} or disconnects → cleanup
    """
    await ws.accept()
    logger.info("AMD WebSocket session started")

    audio_buffer = bytearray()
    early_sent = False
    session_start = time.monotonic()

    # Calculate byte threshold for early decision
    early_bytes = int(EARLY_SEC * SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS)

    try:
        while True:
            message = await ws.receive()

            if message["type"] == "websocket.disconnect":
                break

            # Binary frame = audio data
            if "bytes" in message and message["bytes"]:
                audio_buffer.extend(message["bytes"])

                # Check if we have enough audio for an early decision
                if not early_sent and len(audio_buffer) >= early_bytes:
                    early_sent = True
                    decision = await _process_audio(
                        audio_buffer[:early_bytes], session_start, "early"
                    )
                    await ws.send_text(json.dumps(decision))
                    logger.info(
                        f"Early decision: {decision['label']} "
                        f"(conf={decision['confidence']:.2f}, "
                        f"elapsed={decision['elapsed_ms']}ms)"
                    )

            # Text frame = control message
            elif "text" in message and message["text"]:
                try:
                    ctrl = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                if ctrl.get("type") == "flush":
                    # Final decision using all buffered audio
                    decision = await _process_audio(
                        audio_buffer, session_start, "final"
                    )
                    await ws.send_text(json.dumps(decision))
                    logger.info(
                        f"Final decision: {decision['label']} "
                        f"(conf={decision['confidence']:.2f}, "
                        f"transcript='{decision['transcript'][:60]}...')"
                    )

                elif ctrl.get("type") == "close":
                    break

    except WebSocketDisconnect:
        logger.info("AMD WebSocket client disconnected")
    except Exception as e:
        logger.error(f"AMD WebSocket error: {e}", exc_info=True)
    finally:
        logger.info(
            f"AMD session ended. Total audio: {len(audio_buffer)} bytes "
            f"({len(audio_buffer) / SAMPLE_RATE / SAMPLE_WIDTH:.2f}s)"
        )


async def _process_audio(
    audio_bytes: bytes | bytearray,
    session_start: float,
    decision_type: str
) -> dict:
    """
    Transcribe audio and classify. Runs in a thread pool to avoid
    blocking the asyncio event loop during Whisper inference.
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _process_audio_sync, bytes(audio_bytes), session_start, decision_type
    )
    return result


def _process_audio_sync(
    audio_bytes: bytes,
    session_start: float,
    decision_type: str
) -> dict:
    """
    Synchronous audio processing — runs in thread pool.
    Converts PCM16 bytes → numpy → Whisper → classifier → JSON result.
    """
    # Convert PCM16 bytes to float32 numpy array (Whisper's expected format)
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # Transcribe with Whisper
    transcript = _transcribe(audio_np)

    # Classify transcript
    cls_result = _classify(transcript)

    elapsed_ms = int((time.monotonic() - session_start) * 1000)

    return {
        "type": decision_type,
        "label": cls_result["label"],
        "confidence": round(cls_result["confidence"], 4),
        "proba_human": round(cls_result["proba_human"], 4),
        "transcript": transcript,
        "elapsed_ms": elapsed_ms,
    }
