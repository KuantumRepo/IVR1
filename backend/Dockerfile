FROM python:3.12-slim

WORKDIR /app

# Install dependencies (including those needed for FreeSWITCH ESL if building from source, though greenswitch is pure python)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    espeak-ng \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
