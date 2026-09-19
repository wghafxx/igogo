# ---- frontend ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json ./
RUN yarn install
COPY frontend/ .
ARG REACT_APP_BACKEND_URL
ARG REACT_APP_TELEGRAM_SUPPORT_URL
ARG REACT_APP_TELEGRAM_SUPPORT_HANDLE
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL \
    REACT_APP_TELEGRAM_SUPPORT_URL=$REACT_APP_TELEGRAM_SUPPORT_URL \
    REACT_APP_TELEGRAM_SUPPORT_HANDLE=$REACT_APP_TELEGRAM_SUPPORT_HANDLE \
    GENERATE_SOURCEMAP=false
RUN yarn build

# ---- backend ----
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/build ./static
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
