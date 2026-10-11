"""Make the repository root importable in tests (physics.model, control.rules, common.*)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ROOMS_CONFIG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "rooms.json"))
