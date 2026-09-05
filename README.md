# PyPotter

PyPotter turns trained wand gestures into Home Assistant automations. Version 2 keeps the original OpenCV camera/CLI workflow available and adds a portable, single-user web application for local use.

## Quick start

Python 3.12, 3.13, and 3.14 are supported. Python 3.14 is the primary runtime.

```bash
uv sync --extra dev
uv run pypotter web
```

Open <http://127.0.0.1:8000>. The web workflow accepts a trained spell, persists the result in SQLite, and shows recent casts after reload.

## CLI and library compatibility

The original camera workflow remains available as `python PyPotter.py [video source] [Home Assistant URL] [API token] [remove background] [show windows] [training] [debug FPS]`. The historical modules `PyPotter`, `HassApi`, and `CountsPerSec` remain importable.

The modern CLI provides a deterministic local workflow:

```bash
uv run pypotter recognize incendio
uv run pypotter migrate
```

## Web/API

The FastAPI application factory is `pypotter.api.app:create_app`. System endpoints are `/health` and `/ready`; application endpoints are versioned under `/api/v1`. The checked-in backend-owned contract is [openapi.json](openapi.json). The React TypeScript client lives in `frontend/` and is built with Vite.

## Docker

```bash
docker compose up --build
```

The production image serves the compiled frontend from FastAPI, runs as a non-root user, exposes port 8000, and stores SQLite at `/data/pypotter.db`. Mount or retain the `pypotter-data` volume to preserve history.

## Configuration and migration

Copy `.env.example` to `.env`. All settings use the `PYPOTTER_` prefix. Home Assistant calls are disabled by default; set `PYPOTTER_ENABLE_HOME_ASSISTANT=true`, the URL, and a long-lived token to enable them.

The legacy repository contains a `Training/` image corpus and no database format. `pypotter migrate` creates the SQLite schema without deleting or rewriting those files. Back up any existing database before a migration; `pypotter.migration.backup_database` creates a timestamped copy.

## Development

```bash
uv sync --extra dev
uv run ruff format .
uv run ruff check .
uv run mypy pypotter
uv run pytest --cov
cd frontend && npm install && npm run typecheck && npm test && npm run build
```

GitHub Actions checks Python 3.12–3.14, frontend typechecking/build/tests, OpenAPI drift, package build, and a Docker smoke workflow. Pull requests need no secrets. CI uses least-privilege permissions and cancels superseded runs.

## Architecture and limitations

`pypotter/domain` contains stable spell concepts, `services` contains processing, `persistence` contains the SQLAlchemy repository boundary, `integrations` contains Home Assistant, and `api` contains FastAPI adapters. The initial web release is intentionally local and unauthenticated. PostgreSQL, camera streaming inside the browser, and production authentication remain deferred. The original OpenCV pipeline still requires a camera-capable host and GUI support, so it is not silently enabled in the container.

## Acknowledgements

PyPotter shares inspiration and code from [Raspberry Potter](https://github.com/sean-obrien/rpotter/), [pi_to_potter](https://github.com/mamacker/pi_to_potter), and [computer-vision](https://github.com/nrsyed/computer-vision).
