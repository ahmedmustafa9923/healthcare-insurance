FROM python:3.12-slim

RUN useradd --create-home --uid 10001 seeder
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY seed.py .

USER 10001
CMD ["python", "seed.py"]

