# Build from repository root (needs backend/, ski/, data/, features/, transformations/):
#   docker build -f backend/Dockerfile -t ski-ai-backend .
#
# Run API:
#   docker run --rm -p 10000:10000 -e REDIS_URL=redis://host.docker.internal:6379 ski-ai-backend
#
# Swagger UI: http://localhost:10000/api/docs

# Pin Debian release: default `slim` tracks testing (e.g. trixie) and mirrors can hit hash mismatches.
# Bookworm has stable indexes; deps install from wheels — no `build-essential` needed in most cases.
FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=10000
ENV MPLBACKEND=Agg

COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-prod.txt

# Monorepo packages required by API + RQ worker pipeline
COPY backend/ ./backend/
RUN chmod +x backend/start.sh
COPY ski/ ./ski/
COPY data/ ./data/
COPY features/ ./features/
COPY transformations/ ./transformations/

EXPOSE 10000

CMD ["sh", "backend/start.sh"]
