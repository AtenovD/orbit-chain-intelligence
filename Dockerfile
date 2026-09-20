FROM node:22-alpine AS frontend
ARG VITE_AUTH_REQUIRED=false
ENV VITE_AUTH_REQUIRED=$VITE_AUTH_REQUIRED
ARG VITE_SENTRY_DSN=
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=frontend /frontend/dist ./frontend/dist
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000"]
