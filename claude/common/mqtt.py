"""Thin wrapper around paho-mqtt (v2 API) with JSON payloads and auto-reconnect.

Usage:
    bus = Bus("control")
    bus.subscribe("bldg/+/+/sensor/+", on_reading)   # callback(topic, payload_dict)
    bus.start()                                      # background network thread
    bus.publish(topic, {...}, retain=True)

Delivery is QoS 1 (at-least-once). Consumers must therefore tolerate duplicates —
every message carries `seq` or `ts` for that purpose.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable

import paho.mqtt.client as mqtt

log = logging.getLogger("mqtt")

Callback = Callable[[str, dict[str, Any]], None]


class Bus:
    def __init__(self, client_id: str, host: str | None = None, port: int | None = None) -> None:
        self.host = host or os.getenv("MQTT_HOST", "broker")
        self.port = int(port or os.getenv("MQTT_PORT", "1883"))
        self.client_id = client_id
        self._subs: list[tuple[str, Callback]] = []
        self._connected = threading.Event()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=False)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)
        # Last will: if this process dies, the broker publishes "down" on our health topic.
        self._client.will_set(f"sys/health/{client_id}", json.dumps({"service": client_id, "status": "down"}), qos=1, retain=True)

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        while True:
            try:
                self._client.connect(self.host, self.port, keepalive=30)
                break
            except OSError as e:
                log.warning("broker %s:%s not reachable (%s), retrying", self.host, self.port, e)
                time.sleep(2)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def wait_connected(self, timeout: float = 30) -> bool:
        return self._connected.wait(timeout)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    # -- pub/sub ---------------------------------------------------------------
    def subscribe(self, topic: str, cb: Callback) -> None:
        self._subs.append((topic, cb))
        if self._connected.is_set():
            self._client.subscribe(topic, qos=1)

    def publish(self, topic: str, payload: dict[str, Any], retain: bool = False) -> None:
        info = self._client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.warning("publish to %s failed rc=%s (queued for reconnect)", topic, info.rc)

    def health(self, status: str, detail: str = "") -> None:
        from common.schemas import Health  # local import to avoid cycles
        self.publish(f"sys/health/{self.client_id}", Health(self.client_id, status, detail).to_dict(), retain=True)

    # -- callbacks ---------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        log.info("connected to broker %s:%s (%s)", self.host, self.port, reason_code)
        for topic, _ in self._subs:
            client.subscribe(topic, qos=1)
        self._connected.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        log.warning("disconnected from broker (%s) — paho will reconnect", reason_code)
        self._connected.clear()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8")) if msg.payload else {}
        except json.JSONDecodeError:
            log.warning("non-JSON payload on %s ignored", msg.topic)
            return
        for pattern, cb in self._subs:
            if mqtt.topic_matches_sub(pattern, msg.topic):
                try:
                    cb(msg.topic, payload)
                except Exception:  # a bad message must never kill the network thread
                    log.exception("callback for %s failed", msg.topic)
