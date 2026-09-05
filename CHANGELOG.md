# Changelog

## 2.0.0 - 2026-09-05

- Added a FastAPI `/api/v1` application with health/readiness checks and SQLite-backed recognition history.
- Added a React/TypeScript/Vite web client and a compiled static fallback for portable deployments.
- Added Docker Compose, migration scaffolding, CI, and regression coverage.
- Added direct MQTT event publishing with retained Home Assistant MQTT device discovery.
- Updated the frontend toolchain and supported dependency floors, while keeping the OpenCV 5 upgrade deferred.
- Kept the original `PyPotter.py`, `HassApi.py`, and `CountsPerSec.py` modules available for the camera workflow.
