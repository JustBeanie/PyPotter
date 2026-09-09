from typing import Any
from urllib.parse import urlparse

import requests


def validate_home_assistant_url(url: str) -> str:
    parsed = urlparse(url.rstrip("/"))
    hostname = (parsed.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if not hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Home Assistant URL must not contain credentials or query parameters.")
    if parsed.scheme == "https":
        return url.rstrip("/")
    if parsed.scheme == "http" and hostname in local_hosts:
        return url.rstrip("/")
    raise ValueError("Home Assistant must use HTTPS unless it is running on localhost.")


class HomeAssistantClient:
    def __init__(self, url: str, token: str, timeout: float = 10.0):
        self.url = validate_home_assistant_url(url)
        self.token = token
        self.timeout = timeout

    def trigger_spell(self, spell: str) -> dict[str, Any]:
        response = requests.post(
            f"{self.url}/api/services/automation/trigger",
            json={"entity_id": f"automation.wand_{spell}"},
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=self.timeout,
            allow_redirects=False,
        )
        response.raise_for_status()
        return response.json() if response.content else {}
