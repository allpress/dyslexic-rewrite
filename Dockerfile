# ---- front end -------------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- server ----------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY server/requirements.txt ./server/requirements.txt
RUN pip install -e ".[epub,docs]" -r server/requirements.txt \
 && python -m spacy download en_core_web_sm

COPY server/ ./server/
COPY --from=web /web/dist ./web/dist

ENV PORT=8080 WEB_DIST=/app/web/dist
EXPOSE 8080
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT} --workers 1"]
