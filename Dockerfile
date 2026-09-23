# ---- frontend ----
FROM node:20-alpine AS web
WORKDIR /web
# yarn.lock is committed; the glob keeps COPY from failing if a Git export ever drops it.
COPY frontend/package.json frontend/yarn.lock* ./
RUN if [ -f yarn.lock ]; then yarn install --frozen-lockfile --network-timeout 600000; \
    else echo "WARNING: frontend/yarn.lock missing, resolving dependencies" && yarn install --network-timeout 600000; fi
COPY frontend/ .
ARG REACT_APP_BACKEND_URL
ARG REACT_APP_TELEGRAM_SUPPORT_URL
ARG REACT_APP_TELEGRAM_SUPPORT_HANDLE
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL \
    REACT_APP_TELEGRAM_SUPPORT_URL=$REACT_APP_TELEGRAM_SUPPORT_URL \
    REACT_APP_TELEGRAM_SUPPORT_HANDLE=$REACT_APP_TELEGRAM_SUPPORT_HANDLE \
    GENERATE_SOURCEMAP=false
RUN yarn build

# ---- backend (runtime only: no tests, docs or dev tools) ----
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/*.py ./
COPY --from=web /web/build ./static
RUN useradd --system --uid 10001 --no-create-home app && chown -R app /app
USER app
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
