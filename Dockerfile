FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Safe defaults so `docker run` works without a key. render.yaml switches to Gemma.
ENV DEMO_MODE=true LLM_BACKEND=heuristic WATCH_DIR=/tmp/watched DB_PATH=/tmp/slothsort.db SETTLE_SECONDS=0
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:factory --factory --host 0.0.0.0 --port ${PORT:-10000}"]
