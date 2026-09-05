FROM node:22-bookworm-slim AS frontend-build
WORKDIR /frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY frontend/ ./
RUN pnpm run build

FROM python:3.14-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYPOTTER_DATA_DIR=/data PYPOTTER_DATABASE_URL=sqlite:////data/pypotter.db
WORKDIR /app
RUN groupadd --system pypotter && useradd --system --gid pypotter --home-dir /app pypotter
COPY pyproject.toml README.md LICENSE ./
COPY pypotter/ ./pypotter/
COPY PyPotter.py HassApi.py CountsPerSec.py ./
COPY --from=frontend-build /pypotter/static/ ./pypotter/static/
RUN python -m pip install --no-cache-dir --upgrade pip && python -m pip install --no-cache-dir .
RUN mkdir -p /data && chown -R pypotter:pypotter /app /data
USER pypotter
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')"
CMD ["uvicorn", "pypotter.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
