# ComfyUI + Civitai

Reproducible ComfyUI setup that pulls checkpoints, LoRAs, VAEs, embeddings and ControlNets from the
Civitai API, driven by a single manifest (`models.yaml`). Runs on any remote NVIDIA GPU: Google Colab,
Hostinger GPU VPS, RunPod, Vast.ai, Lambda, etc.

## Layout

| Path | Purpose |
|---|---|
| `models.yaml` | Manifest of Civitai refs and direct URLs to download |
| `custom_nodes.txt` | Git URLs of custom nodes to install |
| `scripts/civitai.py` | CLI: `search`, `info`, `get`, `sync` |
| `scripts/setup.sh` | Installs ComfyUI, nodes, then syncs models |
| `colab/comfyui_colab.ipynb` | Colab notebook (Drive-persisted, Cloudflare tunnel) |
| `docker/`, `docker-compose.yml` | GPU container for VPS hosts |

## Setup

1. Get a Civitai API key: https://civitai.com/user/account -> API Keys.
2. `cp .env.example .env` and fill `CIVITAI_TOKEN`.
3. Push this repo to GitHub (keep `.env` out; it's gitignored).

## Find and add models

```bash
pip install -r requirements.txt
python scripts/civitai.py search "detail" --type LORA --base "SDXL 1.0"
python scripts/civitai.py info 123456          # shows trigger words + files
```
Add the id or URL to `models.yaml`, or grab one ad hoc: `python scripts/civitai.py get <id|url>`.
Files land in `$COMFY_DIR/models/{checkpoints,loras,vae,embeddings,controlnet,...}`. Downloads resume and skip existing files.

## Run on Colab

1. Edit `REPO_URL` in `colab/comfyui_colab.ipynb`, open it in Colab, select a GPU runtime.
2. Add `CIVITAI_TOKEN` under Colab Secrets.
3. Run both cells; open the printed `trycloudflare.com` URL.

Note: Colab free tier is session-limited and policy can restrict Stable Diffusion UIs; Colab Pro or a
paid GPU host is more reliable. Models are stored on Drive so reinstalls are fast.

## Run on Hostinger GPU VPS (or any GPU Linux box)

```bash
git clone <your-repo> && cd <your-repo>
cp .env.example .env && nano .env
docker compose up -d --build        # needs nvidia-container-toolkit
ssh -L 8188:localhost:8188 user@server   # then open http://localhost:8188
```
Without Docker: `bash scripts/setup.sh && python ComfyUI/main.py --listen 0.0.0.0`.
ComfyUI has no auth, so use the SSH tunnel (compose binds to 127.0.0.1) or put it behind a reverse proxy with basic auth.

## Hugging Face

Add files under `hf:` in `models.yaml` (`repo`, `file`, `dest`, optional `rev`). Set `HF_TOKEN` for gated repos.

## Replicate

Replicate is pay-per-second hosted inference, not a server you SSH into, so it doesn't run the ComfyUI UI directly.
Options: (a) call hosted models there via API instead of local ComfyUI, or (b) package this repo's ComfyUI as a
[Cog](https://github.com/replicate/cog) model (`cog push`) to run workflows as API jobs. Option (b) is set up: `cog.yaml` + `predict.py` take an API-format workflow JSON and return images.
```bash
cog login && cog push r8.im/<you>/comfyui   # needs Docker + cog; models in models.yaml get baked in
```
Large model sets make big images; keep `models.yaml` lean for Replicate.

## Notes

- Respect each model's license and Civitai terms; some files require login/token or are early-access.
- Add `--lowvram` / `--fp16-vae` flags to `main.py` for small GPUs (T4 16 GB runs SDXL fine).
