"""
music.py — free local music via ACE-Step running inside ComfyUI.

gen_track(tags, seconds, out_path, lyrics="[inst]", seed=None) -> Path | None
    tags: comma-separated style tags, e.g. "lofi hip hop, mellow, vinyl crackle, 80 bpm, warm piano, instrumental"
    Writes an MP3. Used for (a) low-volume background beds under the shorts, (b) full tracks for the lofi channel.

CLI:
    python music.py --tags "dark ambient, cinematic, slow, synth pads" --seconds 60 --out track.mp3
    python music.py --lofi 6            # six 3-minute lofi tracks into output/music/
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

import netfix  # noqa: E402  (IPv4 + retry hardening)

COMFY_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")
ACE_CKPT = os.getenv("ACESTEP_CHECKPOINT", "ace_step_v1_3.5b.safetensors")
ACE_STEPS = int(os.getenv("ACESTEP_STEPS", "50"))
MUSIC_DIR = Path(os.getenv("MUSIC_DIR", HERE / "output" / "music"))

# Bed styles the shorts pick from (keyed by format)
BED_TAGS = {
    "episode": "dark cinematic ambient, tense synth pads, subtle pulse, minimal, 90 bpm, no drums, instrumental, film score",
    "lesson": "lofi hip hop, calm, warm keys, soft drums, 85 bpm, focus music, instrumental",
    "log": "minimal electronic, glitchy textures, sparse, mysterious, 100 bpm, instrumental",
    "default": "ambient electronic, soft pads, slow, instrumental, background music",
}


def _log(m: str) -> None:
    print(f"      {m}", file=sys.stderr, flush=True)


def _workflow(tags: str, lyrics: str, seconds: float, seed: int) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ACE_CKPT}},
        "2": {"class_type": "TextEncodeAceStepAudio", "inputs": {"clip": ["1", 1], "tags": tags, "lyrics": lyrics, "lyrics_strength": 0.99}},
        "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "4": {"class_type": "EmptyAceStepLatentAudio", "inputs": {"seconds": float(seconds), "batch_size": 1}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["5", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
                "seed": seed, "steps": ACE_STEPS, "cfg": 5.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
            },
        },
        "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveAudioMP3", "inputs": {"audio": ["7", 0], "filename_prefix": "regescore/music/track", "quality": "V0"}},
    }


def gen_track(tags: str, seconds: float, out_path: Path, lyrics: str = "[inst]", seed: Optional[int] = None) -> Optional[Path]:
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    try:
        body = json.dumps({"prompt": _workflow(tags, lyrics, seconds, seed), "client_id": "regescore-music"}).encode()
        req = urllib.request.Request(f"{COMFY_URL}/prompt", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
        if "prompt_id" not in resp:
            raise RuntimeError(f"ComfyUI rejected workflow: {json.dumps(resp)[:400]}")
        pid = resp["prompt_id"]
        deadline = time.time() + 900
        while time.time() < deadline:
            with urllib.request.urlopen(f"{COMFY_URL}/history/{pid}", timeout=30) as r:
                hist = json.load(r)
            if pid in hist:
                st = hist[pid].get("status", {})
                if st.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI error: {json.dumps(st)[:400]}")
                for node_out in hist[pid]["outputs"].values():
                    for a in node_out.get("audio", []):
                        qs = urllib.parse.urlencode({"filename": a["filename"], "subfolder": a.get("subfolder", ""), "type": a.get("type", "output")})
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        with urllib.request.urlopen(f"{COMFY_URL}/view?{qs}", timeout=120) as r, open(out_path, "wb") as f:
                            f.write(r.read())
                        return out_path
            time.sleep(2)
        raise TimeoutError("ACE-Step render timed out")
    except Exception as e:  # noqa: BLE001
        _log(f"music failed: {e}")
        return None


def bed_for(fmt: str, seconds: float, out_path: Path) -> Optional[Path]:
    return gen_track(BED_TAGS.get(fmt, BED_TAGS["default"]), seconds, out_path)


LOFI_STYLES = [
    "lofi hip hop, chill, rainy night, warm vinyl crackle, soft piano, 78 bpm, instrumental",
    "lofi jazz, mellow saxophone, brushed drums, late night cafe, 82 bpm, instrumental",
    "lofi study beats, dreamy guitar, tape saturation, gentle, 75 bpm, instrumental",
    "chillhop, warm rhodes, laid back drums, sunset, 88 bpm, instrumental",
    "ambient lofi, soft pads, distant melody, calm, 70 bpm, instrumental",
    "lofi boom bap, dusty samples, head nod, 90 bpm, instrumental",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--out")
    ap.add_argument("--lofi", type=int, help="generate N lofi tracks (3 min each) into output/music/")
    a = ap.parse_args()
    if a.lofi:
        MUSIC_DIR.mkdir(parents=True, exist_ok=True)
        for i in range(a.lofi):
            style = LOFI_STYLES[i % len(LOFI_STYLES)]
            out = MUSIC_DIR / f"lofi_{int(time.time())}_{i+1:02d}.mp3"
            _log(f"[{i+1}/{a.lofi}] {style}")
            p = gen_track(style, 180, out)
            print(p or "FAILED")
        return
    if not (a.tags and a.out):
        ap.error("--tags and --out required (or --lofi N)")
    p = gen_track(a.tags, a.seconds, Path(a.out))
    print(p or "FAILED")
    sys.exit(0 if p else 1)


if __name__ == "__main__":
    main()
