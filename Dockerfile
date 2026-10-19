FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . \
    && useradd --system --uid 10001 --create-home app \
    && mkdir -p /data \
    && chown app:app /data

USER app

ENTRYPOINT ["niview"]
CMD ["--help"]
