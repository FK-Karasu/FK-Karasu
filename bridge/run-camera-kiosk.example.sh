#!/usr/bin/env bash
set -euo pipefail

export SERVER_URL="https://karasu.uz"
export DEVICE_INGEST_KEY="PASTE_THE_SAME_BRIDGE_KEY_HERE"
export CAMERA_KIOSK_PORT="8090"

exec /home/admina/proAppFootballClub/.venv-camera/bin/python \
  /home/admina/proAppFootballClub/bridge/camera-kiosk.py
