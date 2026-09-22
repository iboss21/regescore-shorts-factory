"""
visuals.py — scene images for the shorts, from free/local generators.

Providers (IMAGE_PROVIDER in .env):
  comfyui      local ComfyUI (default checkpoint Juggernaut-XL v9), best quality, $0, needs GPU
  pollinations free hosted FLUX, no key, ~3 s/image (small watermark is cropped off)
  none         no images -> animated gradient background

gen_images(prompts, out_dir) -> list[Path]  (1080x1920 JPGs, may be shorter than prompts on failures)
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "comfyui").lower()
IMAGE_FALLBACK = os.getenv("IMAGE_FALLBACK", "pollinations").lower()
IMAGE_STYLE = os.getenv(
    "IMAGE_STYLE",
    "cinematic film still, moody, dark teal and amber lighting, shallow depth of field, 35mm, highly detailed, no text, no watermark",
)
IMAGE_NEGATIVE = os.getenv("IMAGE_NEGATIVE", "text, watermark, logo, caption, blurry, deformed, low quality, cartoon, extra fingers")
COMFY_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
COMFY_CKPT = os.getenv("COMFYUI_CHECKPOINT", "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors")
COMFY_STEPS = int(os.getenv("COMFYUI_STEPS", "26"))
COMFY_W, COMFY_H = 832, 1216  # SDXL-native portrait; scaled to 1080x1920 at render
FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")


def _log(msg: str) -> None:
    print(f"      {msg}", file=sys.stderr, flush=True)


def _to_portrait_jpg(src: Path, dst: Path, crop_bottom_frac: float = 0.0) -> Path:
    """Normalise any image to 1080x1920 JPG; optionally crop a strip off the bottom (watermarks)."""
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if crop_bottom_frac > 0:
        vf = f"crop=iw:ih*{1-crop_bottom_frac:.3f}:0:0," + vf
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, "-q:v", "2", str(dst)], check=True)
    return dst


# ---------------------------------------------------------------------------
# Pollinations (hosted, free, no key)
# ---------------------------------------------------------------------------
def _pollinations(prompt: str, dst: Path, seed: int) -> Optional[Path]:
    q = urllib.parse.quote(f"{prompt}, {IMAGE_STYLE}")
    url = f"https://image.pollinations.ai/prompt/{q}?width=1080&height=1920&nologo=true&seed={seed}&model=flux"
    tmp = dst.with_suffix(".raw.jpg")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RegesCoreShorts/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                f.write(r.read())
            if tmp.stat().st_size < 5000:
                raise RuntimeError("tiny response")
            out = _to_portrait_jpg(tmp, dst, crop_bottom_frac=0.06)  # drop watermark strip
            tmp.unlink(missing_ok=True)
            return out
        except Exception as e:  # noqa: BLE001
            _log(f"pollinations retry {attempt+1}: {e}")
            time.sleep(2 + attempt * 3)
    return None


# ---------------------------------------------------------------------------
# ComfyUI (local)
# ---------------------------------------------------------------------------
def _comfy_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{COMFY_URL}/system_stats", timeout=3):
            return True
    except Exception:  # noqa: BLE001
        return False


def _comfy_workflow(prompt: str, seed: int) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": COMFY_CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": f"{prompt}, {IMAGE_STYLE}"}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": IMAGE_NEGATIVE}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": COMFY_W, "height": COMFY_H, "batch_size": 1}},
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                "seed": seed, "steps": COMFY_STEPS, "cfg": 5.5, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0,
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "regescore/scene"}},
    }


def _comfy(prompt: str, dst: Path, seed: int) -> Optional[Path]:
    try:
        body = json.dumps({"prompt": _comfy_workflow(prompt, seed), "client_id": "regescore-shorts"}).encode()
        req = urllib.request.Request(f"{COMFY_URL}/prompt", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            pid = json.load(r)["prompt_id"]
        deadline = time.time() + 300
        while time.time() < deadline:
            with urllib.request.urlopen(f"{COMFY_URL}/history/{pid}", timeout=30) as r:
                hist = json.load(r)
            if pid in hist:
                status = hist[pid].get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI error: {json.dumps(status)[:300]}")
                for node_out in hist[pid]["outputs"].values():
                    for img in node_out.get("images", []):
                        qs = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
                        tmp = dst.with_suffix(".png")
                        with urllib.request.urlopen(f"{COMFY_URL}/view?{qs}", timeout=60) as r, open(tmp, "wb") as f:
                            f.write(r.read())
                        out = _to_portrait_jpg(tmp, dst)
                        tmp.unlink(missing_ok=True)
                        return out
            time.sleep(1.5)
        raise TimeoutError("ComfyUI render timed out")
    except Exception as e:  # noqa: BLE001
        _log(f"comfyui failed: {e}")
        return None


# ---------------------------------------------------------------------------
def gen_images(prompts: List[str], out_dir: Path) -> List[Path]:
    provider = IMAGE_PROVIDER
    if provider == "none" or not prompts:
        return []
    if provider == "comfyui" and not _comfy_alive():
        _log(f"ComfyUI not reachable at {COMFY_URL} -> falling back to {IMAGE_FALLBACK}")
        provider = IMAGE_FALLBACK
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    base_seed = random.randint(1, 10_000_000)
    for i, p in enumerate(prompts):
        p = re.sub(r"\s+", " ", p).strip()
        dst = out_dir / f"scene_{i+1:02d}.jpg"
        got = None
        if provider == "comfyui":
            got = _comfy(p, dst, base_seed + i)
            if got is None and IMAGE_FALLBACK == "pollinations":
                got = _pollinations(p, dst, base_seed + i)
        elif provider == "pollinations":
            got = _pollinations(p, dst, base_seed + i)
        if got:
            paths.append(got)
            _log(f"scene {i+1}/{len(prompts)} ok ({provider})")
    return paths


def default_prompts(title: str, n: int = 7) -> List[str]:
    """Fallback scene prompts when the script has none (e.g. old script files)."""
    seeds = [
        "an AI core awakening inside a dark server rack, glowing cables",
        "a home office at night, one monitor glowing, code scrolling",
        "a rain-soaked city street seen from a car window, driver's hands on the wheel",
        "a ledger notebook on a desk, a single coin on it, dramatic light",
        "abstract data streams converging into a bright point",
        "a phone ringing on a car dashboard at night",
        "an empty server room corridor, blue light, low fog",
    ]
    return [f"{s}, related to: {title}" for s in seeds[:n]]
