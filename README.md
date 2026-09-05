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

## MQTT through Home Assistant

PyPotter does not connect to MQTT directly and `docker-compose.yml` does not start an MQTT broker. The integration path is:

```text
PyPotter -> Home Assistant REST API -> Home Assistant automation -> MQTT broker -> MQTT device
```

When a spell is recognized, PyPotter calls Home Assistant's `automation.trigger` service for `automation.wand_<spell>`. For example, recognizing `incendio` calls `automation.wand_incendio`. The Home Assistant automation then decides what to do; to publish to MQTT, give that automation an action like:

```yaml
actions:
  - action: mqtt.publish
    data:
      topic: home/pypotter/incendio
      payload: incendio
```

Configure the MQTT integration and broker in Home Assistant first, then create or rename the automation entity so its ID matches the spell (`automation.wand_incendio`, `automation.wand_lumos`, and so on). Home Assistant's [MQTT integration](https://www.home-assistant.io/integrations/mqtt) and [`mqtt.publish` action](https://www.home-assistant.io/actions/mqtt.publish/) handle the broker connection and message delivery.

Enable the PyPotter-to-Home-Assistant leg in `.env`:

```dotenv
PYPOTTER_ENABLE_HOME_ASSISTANT=true
PYPOTTER_HOME_ASSISTANT_URL=http://homeassistant:8123
PYPOTTER_HOME_ASSISTANT_TOKEN=your-long-lived-access-token
```

The URL must be reachable from the `pypotter` container. Use the Home Assistant service name when both services share a Compose network, or a reachable host name/IP when Home Assistant runs separately. Do not use `localhost` for a Home Assistant process running outside the PyPotter container.

The checked-in Compose file starts only PyPotter; it intentionally does not provision Home Assistant or a broker. After configuring the automation, verify the full path by submitting a recognition to PyPotter and subscribing to the configured topic with an MQTT client.

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
