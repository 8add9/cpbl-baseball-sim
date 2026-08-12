FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BASEBALL_SIM_DATA_DIR=/data \
    BASEBALL_SIM_RATING_ARTIFACTS=/app/artifacts/generated/ratings \
    BASEBALL_SIM_WEB_DIST=/app/web/dist
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .
COPY artifacts/generated/ratings/ ./artifacts/generated/ratings/
COPY --from=web-build /web/dist/ ./web/dist/
RUN useradd --create-home --uid 10001 baseball && mkdir /data && chown baseball:baseball /data
USER baseball
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "baseball_sim.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
