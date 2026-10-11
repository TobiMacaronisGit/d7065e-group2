"""MQTT topic layout — the one place where topic strings are built.

    bldg/<level>/<room>/sensor/<type>          sensor readings        (co2 | temperature | occupancy)
    bldg/<level>/<room>/actuator/<kind>/cmd    command from control   (retained → restarted actuator recovers)
    bldg/<level>/<room>/actuator/<kind>/state  reached state          (retained)
    bldg/<level>/<room>/plan                   planner suggestion     (retained)
    bldg/<level>/<room>/decision               control decision + reason
    sys/health/<service>                       liveness/heartbeat      (retained)
    sys/fault/<device-id>                      fault injection         {"mode": "stuck|offline|drift|none"}

Wildcard subscriptions used by consumers: `bldg/+/+/sensor/+`, `bldg/#`, `sys/fault/<id>`.
"""


def sensor(level: str, room: str, sensor_type: str) -> str:
    return f"bldg/{level}/{room}/sensor/{sensor_type}"


def actuator_cmd(level: str, room: str, kind: str) -> str:
    return f"bldg/{level}/{room}/actuator/{kind}/cmd"


def actuator_state(level: str, room: str, kind: str) -> str:
    return f"bldg/{level}/{room}/actuator/{kind}/state"


def plan(level: str, room: str) -> str:
    return f"bldg/{level}/{room}/plan"


def decision(level: str, room: str) -> str:
    return f"bldg/{level}/{room}/decision"


def health(service: str) -> str:
    return f"sys/health/{service}"


def fault(device_id: str) -> str:
    return f"sys/fault/{device_id}"


def parse(topic: str) -> dict[str, str]:
    """Split a bldg/... topic into its parts. Raises ValueError on other topics."""
    parts = topic.split("/")
    if len(parts) < 5 or parts[0] != "bldg":
        raise ValueError(topic)
    out = {"level": parts[1], "room": parts[2], "kind": parts[3]}
    if parts[3] == "sensor":
        out["type"] = parts[4]
    elif parts[3] == "actuator":
        out["actuator"] = parts[4]
        out["what"] = parts[5] if len(parts) > 5 else ""
    return out
