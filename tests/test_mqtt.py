import json
from datetime import UTC, datetime

from pypotter.domain.models import KNOWN_SPELLS, Recognition
from pypotter.integrations import mqtt as mqtt_integration
from pypotter.integrations.mqtt import MQTTPublisher, build_discovery_payload


def test_discovery_contains_spell_triggers_and_state_sensors():
    payload = build_discovery_payload(client_id="pypotter", topic_prefix="pypotter")
    components = payload["cmps"]

    assert payload["device"]["identifiers"] == ["pypotter"]
    assert components["last_spell"]["state_topic"] == "pypotter/events"
    assert components["confidence"]["state_topic"] == "pypotter/events"
    assert len(components) == len(KNOWN_SPELLS) + 2
    assert components["trigger_incendio"] == {
        "p": "device_automation",
        "automation_type": "trigger",
        "topic": "pypotter/events",
        "value_template": "{{ value_json.spell }}",
        "payload": "incendio",
        "type": "spell_cast",
        "subtype": "incendio",
    }


class _PublishResult:
    rc = 0


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.published: list[tuple[str, str, int, bool]] = []
        self.subscriptions: list[tuple[str, int]] = []

    def username_pw_set(self, username, password):
        pass

    def will_set(self, topic, payload, qos, retain):
        pass

    def connect_async(self, host, port, keepalive):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def subscribe(self, topic, qos):
        self.subscriptions.append((topic, qos))

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        return _PublishResult()


def test_publisher_advertises_and_publishes_recognitions(monkeypatch):
    fake_client = _FakeClient()
    monkeypatch.setattr(mqtt_integration.mqtt, "Client", lambda *args, **kwargs: fake_client)
    publisher = MQTTPublisher(host="mqtt", username="user", password="pass")

    publisher.start()
    publisher._on_connect(fake_client, None, {}, 0, None)
    published_before_event = len(fake_client.published)
    result = publisher.publish_recognition(
        Recognition("incendio", 0.75, "spell", datetime(2026, 1, 1, tzinfo=UTC))
    )

    assert result is True
    assert fake_client.subscriptions == [("homeassistant/status", 1)]
    assert fake_client.published[0] == ("pypotter/status", "online", 1, True)
    assert fake_client.published[1][0] == "homeassistant/device/pypotter/config"
    assert len(fake_client.published) == published_before_event + 1
    assert json.loads(fake_client.published[-1][1]) == {
        "spell": "incendio",
        "confidence": 0.75,
        "source": "spell",
        "created_at": "2026-01-01T00:00:00+00:00",
    }

    publisher.stop()
