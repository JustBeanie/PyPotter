import json
from pathlib import Path

from pypotter.api.app import app

checked_in = json.loads(Path("openapi.json").read_text(encoding="utf-8"))
generated = app.openapi()
if set(checked_in.get("paths", {})) != set(generated.get("paths", {})):
    raise SystemExit("openapi.json is stale; run python scripts/export_openapi.py")
for path, methods in checked_in["paths"].items():
    if set(methods) != set(generated["paths"][path]):
        raise SystemExit(f"openapi.json is stale for {path}; run python scripts/export_openapi.py")
