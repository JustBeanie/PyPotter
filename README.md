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

## MQTT and Home Assistant discovery

PyPotter connects to an MQTT broker directly and advertises itself to Home Assistant using MQTT discovery. The integration path is:

```text
PyPotter -> MQTT broker -> Home Assistant MQTT discovery -> Home Assistant automations/devices
```

When MQTT is enabled, PyPotter publishes a retained discovery payload to `homeassistant/device/pypotter/config` and publishes recognition events to `pypotter/events`. Home Assistant discovers one PyPotter device with a `Last spell` sensor, a confidence sensor, and one device trigger for every trained spell. A recognition is published as JSON:

```json
{"spell":"incendio","confidence":1.0,"source":"spell","created_at":"2026-01-01T00:00:00+00:00"}
```

In Home Assistant, open an automation, choose the discovered PyPotter device as the trigger, and select the spell trigger (for example, `spell_cast / incendio`). The automation can then control any Home Assistant entity or use the [`mqtt.publish` action](https://www.home-assistant.io/actions/mqtt.publish/) to send a command to another MQTT device. No Home Assistant REST token is needed for this MQTT path.

Enable the MQTT connection in `.env`:

```dotenv
PYPOTTER_ENABLE_MQTT=true
PYPOTTER_MQTT_HOST=mqtt
PYPOTTER_MQTT_PORT=1883
PYPOTTER_MQTT_USERNAME=
PYPOTTER_MQTT_PASSWORD=
PYPOTTER_MQTT_DISCOVERY_PREFIX=homeassistant
PYPOTTER_MQTT_TOPIC_PREFIX=pypotter
PYPOTTER_MQTT_CLIENT_ID=pypotter
```

`docker-compose.yml` includes an Eclipse Mosquitto broker for local development. The default broker is intentionally anonymous and bound to `127.0.0.1:1883`; do not expose this configuration to an untrusted network. Home Assistant must connect to this same broker—for example, use the Docker host address when Home Assistant runs outside this Compose project, or use the `mqtt` service name when it shares the Compose network. The broker persists its data in the `mqtt-data` volume.

To verify the event stream independently:

```bash
mosquitto_sub -h 127.0.0.1 -p 1883 -t 'pypotter/#' -v
```

Then submit a recognition through the web app or API. Home Assistant's [MQTT integration](https://www.home-assistant.io/integrations/mqtt) must be configured with the same broker and discovery prefix. PyPotter also listens for the MQTT birth message on `<discovery_prefix>/status` and republishes discovery when Home Assistant restarts.

## Configuration and migration

Copy `.env.example` to `.env`. All settings use the `PYPOTTER_` prefix. Home Assistant REST calls and MQTT publishing are disabled by default for local Python runs; the Compose setup enables MQTT and points it at its `mqtt` service. See [MQTT and Home Assistant discovery](#mqtt-and-home-assistant-discovery) for the broker settings.

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

`pypotter/domain` contains stable spell concepts, `services` contains processing, `persistence` contains the SQLAlchemy repository boundary, `integrations` contains Home Assistant and MQTT, and `api` contains FastAPI adapters. The initial web release is intentionally local and unauthenticated. PostgreSQL, camera streaming inside the browser, and production authentication remain deferred. The original OpenCV pipeline still requires a camera-capable host and GUI support, so it is not silently enabled in the container.

## Acknowledgements

PyPotter shares inspiration and code from [Raspberry Potter](https://github.com/sean-obrien/rpotter/), [pi_to_potter](https://github.com/mamacker/pi_to_potter), and [computer-vision](https://github.com/nrsyed/computer-vision).
