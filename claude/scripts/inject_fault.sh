#!/usr/bin/env bash
# Fault injection for the evaluation (rubric D). Examples:
#   scripts/inject_fault.sh A109-co2 stuck      # CO₂ sensor freezes on its last value
#   scripts/inject_fault.sh A109-co2 offline    # sensor stops reporting
#   scripts/inject_fault.sh A109-co2 drift      # slow bias, +50 ppm per simulated hour
#   scripts/inject_fault.sh A109-vent stuck     # damper does not move
#   scripts/inject_fault.sh A109-vent slow      # damper at 1/4 speed
#   scripts/inject_fault.sh A109-co2 none       # clear
# Process-level faults use Compose directly:
#   docker compose kill sensor-co2-a109 && sleep 30 && docker compose start sensor-co2-a109
#   docker compose stop broker      # every service must survive this and reconnect
#   docker compose restart buildsim # devices must re-register (empty in-memory state)
set -euo pipefail
DEVICE="${1:?device id, e.g. A109-co2}"
MODE="${2:?mode: stuck|offline|drift|slow|none}"
docker compose exec broker mosquitto_pub -h localhost -t "sys/fault/${DEVICE}" -m "{\"mode\":\"${MODE}\",\"by\":\"inject_fault.sh\"}" -q 1
echo "sys/fault/${DEVICE} ← ${MODE}"
