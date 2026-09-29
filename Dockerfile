# Build frontend with Node
FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Python runtime for FastAPI and WebSockets
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY sessioniq/pyproject.toml ./sessioniq/
COPY sessioniq/app ./sessioniq/app
COPY sessioniq/server_main.py ./sessioniq/

RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    websockets \
    google-cloud-firestore \
    google-cloud-storage \
    google-adk \
    google-genai \
    python-multipart

# Copy built frontend assets
COPY --from=frontend-builder /frontend/dist /app/frontend_dist

WORKDIR /app/sessioniq
ENV PYTHONPATH=/app/sessioniq

CMD ["python", "-m", "uvicorn", "server_main:app", "--host", "0.0.0.0", "--port", "8080"]
