FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

#   docker run --env-file .env digest-engine --config configs/torchlab-ai.yml
ENTRYPOINT ["run-digest"]
CMD ["--config", "configs/torchlab-ai.yml"]
