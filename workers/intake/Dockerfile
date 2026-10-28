FROM python:3.12-slim

RUN useradd --create-home --uid 10001 worker
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

USER 10001
CMD ["python", "worker.py"]

