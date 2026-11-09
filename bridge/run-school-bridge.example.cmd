@echo off
REM Local bridge for Hikvision Face ID terminals.

set SERVER_URL=https://karasu.uz
set DEVICE_INGEST_KEY=PASTE_KEY_FROM_SETTINGS
set HIK_USER=admin
set HIK_PASS=PASTE_HIKVISION_PASSWORD
set HIK_SYNC_INTERVAL_MS=60000
set HIK_SYNC_RECREATE_USERS=false

REM Optional. If empty, bridge downloads terminal list from website Settings -> Hikvision.
REM set HIK_DEVICES_JSON=[{"name":"entry","ip":"192.168.68.107","protocol":"https","port":443,"doorNo":1},{"name":"exit","ip":"192.168.68.104","protocol":"https","port":443,"doorNo":1}]

cd /d "%~dp0.."
node bridge\hikvision-school-bridge.mjs
