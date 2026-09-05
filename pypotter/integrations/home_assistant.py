from typing import Any

import requests


class HomeAssistantClient:
    def __init__(self, url: str, token: str, timeout: float = 10.0):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def trigger_spell(self, spell: str) -> dict[str, Any]:
        response = requests.post(
            f"{self.url}/api/services/automation/trigger",
            json={"entity_id": f"automation.wand_{spell}"},
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json() if response.content else {}
