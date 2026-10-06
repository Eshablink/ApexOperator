FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY frontend ./frontend
COPY workspace ./workspace

RUN pip install --upgrade pip \
    && pip install . \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "apexoperator.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
