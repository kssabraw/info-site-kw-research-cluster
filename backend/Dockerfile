# Mirrors the services/nlp Dockerfile pattern from showup-local (PRD §14.2):
# slim Python base, install the package, run uvicorn on Railway's $PORT.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

# M12 SIE: the locked spaCy lemmatizer (en_core_web_sm) — downloaded at build
# time into the image (sie-module-plan §9 #1; matches the installed spaCy minor).
RUN python -m spacy download en_core_web_sm

# Railway injects $PORT. Default to 8000 for local docker runs.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
