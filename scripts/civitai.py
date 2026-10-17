#!/usr/bin/env python3
"""Civitai CLI for ComfyUI: search, inspect and download models into the right folders.

Usage:
  civitai.py search "detail tweaker" --type LORA [--base "SDXL 1.0"]
  civitai.py info 12345                      # model id, version id or civitai URL
  civitai.py get https://civitai.com/models/12345?modelVersionId=67890
  civitai.py sync models.yaml                # download everything in the manifest

Env: CIVITAI_TOKEN (required for gated/NSFW/early-access files), COMFY_DIR (default ./ComfyUI)
"""
import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
import yaml

API = "https://civitai.com/api/v1"

# Civitai model type -> ComfyUI models subfolder
TYPE_DIRS = {
    "Checkpoint": "checkpoints",
    "LORA": "loras",
    "LoCon": "loras",
    "DoRA": "loras",
    "TextualInversion": "embeddings",
    "VAE": "vae",
    "Controlnet": "controlnet",
    "Upscaler": "upscale_models",
    "Hypernetwork": "hypernetworks",
}


def session():
    s = requests.Session()
    token = os.environ.get("CIVITAI_TOKEN")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    s.headers["User-Agent"] = "comfyui-civitai-repo/1.0"
    return s


def comfy_models_dir() -> Path:
    return Path(os.environ.get("COMFY_DIR", "ComfyUI")) / "models"


def parse_ref(ref: str):
    """Return (model_id, version_id) from an id or civitai URL."""
    ref = str(ref)
    if ref.isdigit():
        return None, int(ref)  # bare number is treated as a version id
    u = urlparse(ref)
    m = re.search(r"/models/(\d+)", u.path)
    model_id = int(m.group(1)) if m else None
    v = parse_qs(u.query).get("modelVersionId")
    version_id = int(v[0]) if v else None
    m2 = re.search(r"/api/download/models/(\d+)", u.path)
    if m2:
        version_id = int(m2.group(1))
    return model_id, version_id


def get_version(s, ref):
    model_id, version_id = parse_ref(ref)
    if version_id is None:
        r = s.get(f"{API}/models/{model_id}", timeout=30)
        r.raise_for_status()
        version_id = r.json()["modelVersions"][0]["id"]  # newest first
    r = s.get(f"{API}/model-versions/{version_id}", timeout=30)
    r.raise_for_status()
    return r.json()


def download(s, version: dict, dest_override: str | None = None):
    mtype = version["model"]["type"]
    sub = dest_override or TYPE_DIRS.get(mtype)
    if not sub:
        sys.exit(f"Unmapped model type {mtype!r}; set 'dest' in the manifest.")
    files = version["files"]
    f = next((x for x in files if x.get("primary")), files[0])
    out_dir = comfy_models_dir() / sub
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f["name"]
    size = int(f.get("sizeKB", 0) * 1024)
    if out.exists() and (size == 0 or abs(out.stat().st_size - size) < 4096):
        print(f"skip   {out} (exists)")
        return out

    part = out.with_suffix(out.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    print(f"get    {version['model']['name']} / {version['name']} -> {out}")
    with s.get(f["downloadUrl"], headers=headers, stream=True, timeout=60) as r:
        if r.status_code in (401, 403):
            sys.exit("Auth required: set CIVITAI_TOKEN (https://civitai.com/user/account).")
        r.raise_for_status()
        mode = "ab" if r.status_code == 206 else "wb"
        done = have if mode == "ab" else 0
        with open(part, mode) as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if size:
                    print(f"\r       {done / size:6.1%}", end="", flush=True)
    print()
    part.rename(out)
    return out


def cmd_search(a):
    s = session()
    params = {"query": a.query, "limit": a.limit, "sort": "Most Downloaded"}
    if a.type:
        params["types"] = a.type
    if a.base:
        params["baseModels"] = a.base
    r = s.get(f"{API}/models", params=params, timeout=30)
    r.raise_for_status()
    for m in r.json()["items"]:
        v = m["modelVersions"][0] if m["modelVersions"] else {}
        print(f"{m['id']:>8}  v{v.get('id', '-'):<8} {m['type']:<10} {v.get('baseModel', ''):<14} {m['name']}")


def cmd_info(a):
    v = get_version(session(), a.ref)
    print(f"{v['model']['name']} / {v['name']}  [{v['model']['type']}, {v.get('baseModel')}]")
    print(f"version id: {v['id']}  model id: {v['modelId']}")
    if v.get("trainedWords"):
        print("trigger words:", ", ".join(v["trainedWords"]))
    for f in v["files"]:
        print(f"file: {f['name']}  {f.get('sizeKB', 0) / 1024:.0f} MB")


def cmd_get(a):
    s = session()
    for ref in a.refs:
        download(s, get_version(s, ref), a.dest)


def cmd_sync(a):
    s = session()
    manifest = yaml.safe_load(Path(a.manifest).read_text()) or {}
    for entry in manifest.get("civitai") or []:
        ref = entry["id"] if isinstance(entry, dict) else entry
        dest = entry.get("dest") if isinstance(entry, dict) else None
        download(s, get_version(s, ref), dest)
    hf_token = os.environ.get("HF_TOKEN")
    hf_headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    # Hugging Face files: {repo, file, dest, [rev], [name]}
    for e in manifest.get("hf") or []:
        url = f"https://huggingface.co/{e['repo']}/resolve/{e.get('rev', 'main')}/{e['file']}"
        fetch_url(url, e["dest"], e.get("name") or e["file"].rsplit("/", 1)[-1], hf_headers)
    # Direct links: {url, dest, [name]}
    for e in manifest.get("urls") or []:
        name = e.get("name") or e["url"].rsplit("/", 1)[-1].split("?")[0]
        headers = hf_headers if "huggingface.co" in e["url"] else {}
        fetch_url(e["url"], e["dest"], name, headers)


def fetch_url(url, dest, name, headers):
    out_dir = comfy_models_dir() / dest
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / name
    part = out.with_suffix(out.suffix + ".part")
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        if r.status_code in (401, 403):
            sys.exit("Auth required: set HF_TOKEN (https://huggingface.co/settings/tokens).")
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0))
        if out.exists() and (total == 0 or out.stat().st_size == total):
            print(f"skip   {out} (exists, {out.stat().st_size / 1e9:.2f} GB)")
            return
        print(f"get    {url} -> {out} ({total / 1e9:.2f} GB)")
        done, next_mark = 0, 1 << 30
        with open(part, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if done >= next_mark:
                    print(f"       {done / 1e9:.1f} / {total / 1e9:.1f} GB", flush=True)
                    next_mark += 1 << 30
    if total and part.stat().st_size != total:
        sys.exit(f"Incomplete download for {name}: {part.stat().st_size} of {total} bytes")
    part.replace(out)
    print(f"ok     {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)

    sp = sub.add_parser("search"); sp.add_argument("query")
    sp.add_argument("--type"); sp.add_argument("--base"); sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("info"); sp.add_argument("ref"); sp.set_defaults(fn=cmd_info)

    sp = sub.add_parser("get"); sp.add_argument("refs", nargs="+")
    sp.add_argument("--dest", help="override models subfolder"); sp.set_defaults(fn=cmd_get)

    sp = sub.add_parser("sync"); sp.add_argument("manifest", nargs="?", default="models.yaml")
    sp.set_defaults(fn=cmd_sync)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
