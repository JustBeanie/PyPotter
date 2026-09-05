"""Export the backend-owned OpenAPI contract for review and client generation."""

import json
from pathlib import Path

from pypotter.api.app import app

Path("openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
