FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
RUN mkdir -p /app/state

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    STATE_FILE=/app/state/notified.json

CMD ["python", "-m", "src.main"]