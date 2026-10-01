"""End-to-end test: the loop closes THROUGH BuildSim.

    docker compose up --build -d && pytest -m e2e tests/

The test plays the role of `control` for one command: it publishes a retained ventilation command for
A109 and asserts that (1) the actuator process applies it and BuildSim shows the reached state,
(2) the physics engine reads that state back, and (3) the next CO₂ readings are not higher than before
(an unoccupied room decays, an occupied one rises more slowly). Finally it hands control back.
"""
import json
import os
import time

import httpx
import paho.mqtt.client as mqtt
import pytest

from common.schemas import now_iso

BUILDSIM = os.getenv("BUILDSIM_URL", "http://127.0.0.1:9090")
PHYSICS = os.getenv("PHYSICS_URL", "http://127.0.0.1:8090")
PIPELINE = os.getenv("PIPELINE_URL", "http://127.0.0.1:8092")
MQTT_HOST, MQTT_PORT = os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883"))
ROOM, LEVEL = "A109", "level0"

pytestmark = pytest.mark.e2e


def wait_for(pred, timeout=30, every=1.0, what="condition"):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(every)
    raise AssertionError(f"timeout waiting for {what}")


def publish(topic: str, payload: dict, retain: bool = True) -> None:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e-test")
    c.connect(MQTT_HOST, MQTT_PORT)
    c.loop_start()
    c.publish(topic, json.dumps(payload), qos=1, retain=retain).wait_for_publish(5)
    c.loop_stop()
    c.disconnect()


def latest_co2() -> float:
    rows = httpx.get(f"{PIPELINE}/history", params={"room": ROOM, "type": "co2", "minutes": 5}).json()
    assert rows, "no CO₂ readings in the pipeline yet"
    return float(rows[-1]["value"])


def test_command_reaches_buildsim_physics_and_next_reading():
    assert httpx.get(f"{BUILDSIM}/healthz").status_code == 200
    wait_for(lambda: httpx.get(f"{PIPELINE}/history", params={"room": ROOM, "type": "co2", "minutes": 5}).json(),
             timeout=60, what="first CO₂ readings")
    before = latest_co2()

    cmd = {"actuator_id": f"{ROOM}-vent", "level": LEVEL, "room": ROOM, "kind": "vent", "target": 3,
           "reason": "e2e test", "issued_by": "control", "sim_ts": now_iso(), "seq": 10_000_000, "ts": now_iso()}
    publish(f"bldg/{LEVEL}/{ROOM}/actuator/vent/cmd", cmd)

    # (1) actuator applied it, BuildSim shows the reached state (0.5 level/s → ≤ 6 s + reporting)
    wait_for(lambda: float(httpx.get(f"{BUILDSIM}/api/actuators/{ROOM}-vent").json()["state"]) >= 3, timeout=30, what="BuildSim actuator = 3")
    # (2) physics read it back
    wait_for(lambda: float(httpx.get(f"{PHYSICS}/rooms/{ROOM}").json()["vent_level"]) >= 3, timeout=15, what="physics sees vent 3")
    # (3) next readings reflect it: after ~20 wall s (= 20 sim-min at 60×) CO₂ must not be above `before` + noise
    time.sleep(20)
    after = latest_co2()
    assert after <= before + 60, f"full ventilation did not lower/hold CO₂: {before} → {after}"

    # hand the room back to control: an out-of-range retained command is rejected, so publish a sane one
    cmd.update(target=0, reason="e2e test cleanup", ts=now_iso(), seq=10_000_001)
    publish(f"bldg/{LEVEL}/{ROOM}/actuator/vent/cmd", cmd)
