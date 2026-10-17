#!/usr/bin/env bash
# Install ComfyUI + custom nodes + Civitai models. Works on Colab, Hostinger GPU VPS, RunPod, etc.
# Usage: COMFY_DIR=/content/ComfyUI CIVITAI_TOKEN=xxx bash scripts/setup.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export COMFY_DIR="${COMFY_DIR:-$REPO_DIR/ComfyUI}"

[ -d "$COMFY_DIR/.git" ] || git clone https://github.com/comfyanonymous/ComfyUI "$COMFY_DIR"
pip install -q -r "$COMFY_DIR/requirements.txt" -r "$REPO_DIR/requirements.txt"

mkdir -p "$COMFY_DIR/custom_nodes"
while read -r url; do
  [ -z "$url" ] && continue
  dir="$COMFY_DIR/custom_nodes/$(basename "$url")"
  [ -d "$dir" ] || git clone --depth 1 "$url" "$dir"
  [ -f "$dir/requirements.txt" ] && pip install -q -r "$dir/requirements.txt" || true
done < "$REPO_DIR/custom_nodes.txt"

python "$REPO_DIR/scripts/civitai.py" sync "$REPO_DIR/models.yaml"
echo "Done. Start with: python $COMFY_DIR/main.py --listen 0.0.0.0 --port 8188"
