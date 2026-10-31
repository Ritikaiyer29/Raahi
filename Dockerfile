# Stage 1: build the React frontend
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI serving API + built frontend
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Asia/Kolkata
WORKDIR /srv
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY supabase ./supabase
COPY --from=web /web/dist ./frontend/dist
ARG GIT_COMMIT=dev
ENV GIT_COMMIT=${GIT_COMMIT}
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
