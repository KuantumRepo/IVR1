# ═══════════════════════════════════════════════════════════════════════════════
# Whisper AMD Sidecar — AI-Based Answering Machine Detection
# ═══════════════════════════════════════════════════════════════════════════════
# CPU-only, INT8 quantized faster-whisper service.
# Accepts PCM16 16kHz mono audio over WebSocket, transcribes, and classifies
# as HUMAN or MACHINE using TF-IDF + Logistic Regression text classifier.
#
# This is Layer 2 of the 3-layer AMD system — invoked only when mod_amd
# (Layer 1) returns ambiguous results, keeping CPU load manageable.
# ═══════════════════════════════════════════════════════════════════════════════

FROM python:3.11-slim

# Install system dependencies:
# - libsndfile1: audio file I/O for soundfile/librosa
# - ffmpeg: audio format conversion (faster-whisper fallback)
# - curl: healthcheck probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose WebSocket port
EXPOSE 8080

# Healthcheck — server must respond to /healthz
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
    CMD curl -sf http://localhost:8080/healthz || exit 1

# Start the WebSocket AMD server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
