FROM python:3.12-slim

WORKDIR /app

# System deps for audio processing and PostgreSQL
RUN apt-get update && apt-get install -y \
    libpq-dev \
    espeak-ng \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (no PyTorch!)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Kokoro ONNX model files at build time (cached in Docker layer)
# Cache bust: 2026-04-08
RUN curl -sL -o /app/kokoro-v1.0.onnx \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx && \
    curl -sL -o /app/voices-v1.0.bin \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
