"""ISO-8601 helpers. Standard library only, on purpose.

The pure-logic modules (control/rules.py, actuator/device.py, physics/model.py) must stay importable
without an HTTP client or an MQTT client, so that their unit tests run anywhere. Anything that parses
or formats a timestamp imports it from here, never from common/clock.py (which needs httpx).
"""
from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """Current wall-clock time, UTC, ISO-8601 with milliseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 timestamp; accepts a trailing 'Z'."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def seconds_between(a: str | None, b: str) -> float:
    """Non-negative seconds from timestamp `a` to `b`; 0 when `a` is unknown."""
    if a is None:
        return 0.0
    return max(0.0, (parse_iso(b) - parse_iso(a)).total_seconds())
