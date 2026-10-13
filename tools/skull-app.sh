#!/usr/bin/env bash
# Start the skull control app (systemd user service) and open it as an app window.
set -euo pipefail
URL=http://localhost:8000
systemctl --user start skull-brain.service
for _ in $(seq 1 50); do
  curl -sf -o /dev/null "$URL/" && break
  sleep 0.2
done
exec omarchy-launch-webapp "$URL"
