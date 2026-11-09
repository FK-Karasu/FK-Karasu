#!/usr/bin/env bash
set -euo pipefail

export SERVER_URL="https://karasu.uz"
export DEVICE_INGEST_KEY="PASTE_KEY_FROM_SETTINGS"
export HIK_USER="admin"
export HIK_PASS="PASTE_HIKVISION_PASSWORD"
export HIK_SYNC_INTERVAL_MS="60000"
export HIK_SYNC_RECREATE_USERS="false"

# Optional. If empty, bridge downloads terminal list from website Settings -> Hikvision.
# export HIK_DEVICES_JSON='[
#   {"name":"entry","ip":"192.168.68.107","protocol":"https","port":443,"doorNo":1},
#   {"name":"exit","ip":"192.168.68.104","protocol":"https","port":443,"doorNo":1}
# ]'

cd "$(dirname "$0")/.."
node bridge/hikvision-school-bridge.mjs
