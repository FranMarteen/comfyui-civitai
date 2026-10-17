#!/usr/bin/env bash
set -euo pipefail
# First boot installs ComfyUI + nodes + models into the persistent /data volume.
if [ ! -f "$COMFY_DIR/main.py" ]; then
  bash /app/scripts/setup.sh
else
  python /app/scripts/civitai.py sync /app/models.yaml   # pick up manifest changes
fi
exec python "$COMFY_DIR/main.py" --listen 0.0.0.0 --port 8188 "$@"
