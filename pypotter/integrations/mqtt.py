"""MQTT event publishing and Home Assistant MQTT discovery."""

import ipaddress
import json
import logging
import socket
from threading import Lock
from typing import Any

import paho.mqtt.client as mqtt

from pypotter.domain.models import KNOWN_SPELLS, Recognition

logger = logging.getLogger("pypotter.mqtt")


def _is_loopback_host(host: str) -> bool:
    # `mqtt` is the private Docker Compose service name. It is not publicly
    # routable from the deployment, so credentials are sufficient there.
    if host.lower() in {"localhost", "mqtt"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        try:
            return all(
                ipaddress.ip_address(info[4][0]).is_loopback
                for info in socket.getaddrinfo(host, None)
            )
        except (OSError, ValueError):
            return False


def _topic(prefix: str, suffix: str) -> str:
    return f"{prefix.strip('/')}/{suffix}"


def configure_client(
    client: mqtt.Client, host: str, username: str | None, password: str | None, tls: bool
) -> None:
    if not username or not password:
        raise ValueError("MQTT requires a username and password; anonymous access is disabled.")
    if not _is_loopback_host(host) and not tls:
        raise ValueError("MQTT TLS is required for non-local brokers.")
    client.username_pw_set(username, password)
    if tls:
        client.tls_set()
    client.max_queued_messages_set(32)


def build_discovery_payload(
    *,
    client_id: str,
    topic_prefix: str,
    version: str = "2.1.0",
    spells: tuple[str, ...] = KNOWN_SPELLS,
) -> dict[str, Any]:
    """Build one Home Assistant device-discovery payload for PyPotter."""
    events_topic = _topic(topic_prefix, "events")
    components: dict[str, dict[str, Any]] = {
        "last_spell": {
            "p": "sensor",
            "name": "Last spell",
            "unique_id": f"{client_id}_last_spell",
            "state_topic": events_topic,
            "value_template": "{{ value_json.spell }}",
            "icon": "mdi:auto-fix",
        },
        "confidence": {
            "p": "sensor",
            "name": "Last spell confidence",
            "unique_id": f"{client_id}_confidence",
            "state_topic": events_topic,
            "value_template": "{{ value_json.confidence }}",
            "state_class": "measurement",
            "suggested_display_precision": 3,
        },
    }
    for spell in spells:
        components[f"trigger_{spell}"] = {
            "p": "device_automation",
            "automation_type": "trigger",
            "topic": events_topic,
            "value_template": "{{ value_json.spell }}",
            "payload": spell,
            "type": "spell_cast",
            "subtype": spell,
        }

    return {
        "device": {
            "identifiers": [client_id],
            "name": "PyPotter",
            "manufacturer": "PyPotter",
            "model": "Wand gesture recognizer",
            "sw_version": version,
        },
        "o": {
            "name": "PyPotter",
            "sw": version,
            "support_url": "https://github.com/JustBeanie/PyPotter",
        },
        "cmps": components,
    }


class MQTTPublisher:
    """Publish recognitions and advertise PyPotter as an MQTT device."""

    def __init__(
        self,
        *,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        discovery_prefix: str = "homeassistant",
        topic_prefix: str = "pypotter",
        client_id: str = "pypotter",
        tls: bool = False,
        version: str = "2.1.0",
        spells: tuple[str, ...] = KNOWN_SPELLS,
    ):
        self.events_topic = _topic(topic_prefix, "events")
        self.status_topic = _topic(topic_prefix, "status")
        self.discovery_topic = _topic(discovery_prefix, f"device/{client_id.strip('/')}/config")
        self.home_assistant_status_topic = _topic(discovery_prefix, "status")
        self._client_id = client_id
        self._topic_prefix = topic_prefix
        self._version = version
        self._spells = tuple(spells)
        self._discovery_lock = Lock()
        self._connected = False
        self._started = False

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        configure_client(self._client, host, username, password, tls)
        self._client.will_set(self.status_topic, payload="offline", qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._host = host
        self._port = port

    def start(self) -> None:
        """Start Paho's reconnecting network loop without blocking app startup."""
        if self._started:
            return
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()
        self._started = True

    def stop(self) -> None:
        """Publish an offline status and stop the MQTT network loop."""
        if not self._started:
            return
        try:
            if self._connected:
                published = self._client.publish(self.status_topic, "offline", qos=1, retain=True)
                if published.rc == mqtt.MQTT_ERR_SUCCESS:
                    published.wait_for_publish(timeout=1)
        except RuntimeError:
            logger.warning("Could not publish MQTT offline status")
        finally:
            self._client.disconnect()
            self._client.loop_stop()
            self._connected = False
            self._started = False

    def publish_recognition(self, recognition: Recognition) -> bool:
        """Publish a recognition event; return false while the broker is unavailable."""
        if not self._connected:
            logger.warning("MQTT broker is not connected; recognition was not published")
            return False
        payload = json.dumps(
            {
                "spell": recognition.spell,
                "confidence": recognition.confidence,
                "source": recognition.source,
                "created_at": recognition.created_at.isoformat(),
            },
            separators=(",", ":"),
        )
        try:
            result = self._client.publish(self.events_topic, payload, qos=1, retain=False)
        except Exception:
            logger.exception("Unable to publish MQTT recognition")
            return False
        if int(result.rc) != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("MQTT recognition publish failed with return code %s", result.rc)
            return False
        return True

    def update_spells(self, spells: list[str]) -> None:
        """Refresh retained discovery after adding a custom spell."""
        with self._discovery_lock:
            if tuple(spells) == self._spells:
                return
            self._spells = tuple(spells)
            if self._connected:
                self._publish_discovery(self._client)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        if reason_code != 0:
            logger.warning("MQTT connection refused: %s", reason_code)
            return
        self._connected = True
        client.subscribe(self.home_assistant_status_topic, qos=1)
        client.publish(self.status_topic, "online", qos=1, retain=True)
        with self._discovery_lock:
            self._publish_discovery(client)
        logger.info("Connected to MQTT broker")

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        self._connected = False
        logger.info("Disconnected from MQTT broker: %s", reason_code)

    def _on_message(self, client: mqtt.Client, userdata: Any, message: Any) -> None:
        if message.topic == self.home_assistant_status_topic and message.payload == b"online":
            with self._discovery_lock:
                self._publish_discovery(client)

    def _publish_discovery(self, client: mqtt.Client) -> None:
        result = client.publish(
            self.discovery_topic,
            json.dumps(
                build_discovery_payload(
                    client_id=self._client_id,
                    topic_prefix=self._topic_prefix,
                    version=self._version,
                    spells=self._spells,
                ),
                separators=(",", ":"),
            ),
            qos=1,
            retain=True,
        )
        if int(result.rc) != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("Home Assistant MQTT discovery publish failed: %s", result.rc)
