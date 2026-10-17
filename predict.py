"""Replicate/Cog wrapper: run a ComfyUI API-format workflow and return the images.

Export a workflow from ComfyUI with "Save (API Format)" and pass its JSON as `workflow`.
"""
import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

import requests
from cog import BasePredictor, Input, Path as CogPath

COMFY_DIR = os.environ.get("COMFY_DIR", "/src/ComfyUI")
HOST = "http://127.0.0.1:8188"


class Predictor(BasePredictor):
    def setup(self):
        self.proc = subprocess.Popen(
            ["python", f"{COMFY_DIR}/main.py", "--listen", "127.0.0.1", "--port", "8188", "--dont-print-server"]
        )
        for _ in range(120):
            try:
                requests.get(f"{HOST}/system_stats", timeout=2).raise_for_status()
                return
            except requests.RequestException:
                time.sleep(1)
        raise RuntimeError("ComfyUI failed to start")

    def predict(
        self,
        workflow: str = Input(description="ComfyUI workflow in API format (JSON string)"),
    ) -> list[CogPath]:
        prompt_id = requests.post(f"{HOST}/prompt", json={"prompt": json.loads(workflow)}).json()["prompt_id"]
        while True:
            hist = requests.get(f"{HOST}/history/{prompt_id}").json()
            if prompt_id in hist:
                break
            time.sleep(0.5)

        out = []
        for node in hist[prompt_id]["outputs"].values():
            for img in node.get("images", []):
                q = urllib.parse.urlencode(img)
                path = Path("/tmp") / img["filename"]
                path.write_bytes(requests.get(f"{HOST}/view?{q}").content)
                out.append(CogPath(path))
        return out
