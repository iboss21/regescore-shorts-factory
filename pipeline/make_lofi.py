"""
make_lofi.py — long-form music videos (lofi / ambient / focus) from free local AI.

  ACE-Step (ComfyUI) generates N tracks ─► crossfaded into one mix
  ComfyUI (Juggernaut-XL) paints one 16:9 scene ─► very slow zoom + grain for the whole runtime
  FFmpeg renders 1920x1080 ─► result.json compatible with the n8n workflow (post via from_result)

Usage:
  python make_lofi.py --minutes 30 --style lofi
  python make_lofi.py --minutes 60 --style ambient --title "RegesCore Radio: 1 hour of dark focus music"
Styles: lofi | ambient | synth | piano
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

import netfix  # noqa: E402  (IPv4 + retry hardening)

import music  # noqa: E402
import visuals  # noqa: E402

OUT_ROOT = Path(os.getenv("OUTPUT_DIR", HERE / "output"))
FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_BIN", "ffprobe")
TRACK_SECONDS = int(os.getenv("LOFI_TRACK_SECONDS", "180"))

STYLES = {
    "lofi": {
        "tags": [
            "lofi hip hop, chill, rainy night, warm vinyl crackle, soft piano, 78 bpm, instrumental",
            "lofi jazz, mellow saxophone, brushed drums, late night cafe, 82 bpm, instrumental",
            "lofi study beats, dreamy guitar, tape saturation, gentle, 75 bpm, instrumental",
            "chillhop, warm rhodes, laid back drums, sunset, 88 bpm, instrumental",
            "ambient lofi, soft pads, distant melody, calm, 70 bpm, instrumental",
            "lofi boom bap, dusty samples, head nod, 90 bpm, instrumental",
        ],
        "scene": "a cozy home office at night, one monitor glowing with code, rain on the window, city lights bokeh, "
                 "a sleeping cat on the desk, warm lamp, lofi anime film still, wide shot",
        "title": "RegesCore Radio - lofi beats to build your empire to",
        "tags_yt": ["lofi", "lofi hip hop", "study music", "focus music", "chill beats", "work music", "coding music", "regescore"],
    },
    "ambient": {
        "tags": [
            "dark ambient, cinematic pads, slow evolving drones, distant pulse, 60 bpm, instrumental",
            "ambient electronic, deep space, soft synth swells, meditative, instrumental",
            "cinematic ambient, tension and release, subtle piano, reverb, instrumental",
            "ambient drone, warm analog, slow, night, instrumental",
        ],
        "scene": "a vast server room at night seen from above, endless racks with blue and amber LEDs, thin fog, "
                 "one figure-less corridor of light, cinematic wide shot, film still",
        "title": "RegesCore Radio - dark ambient for deep work",
        "tags_yt": ["dark ambient", "deep work music", "focus music", "ambient", "concentration", "regescore"],
    },
    "synth": {
        "tags": [
            "synthwave, retro 80s, driving arpeggios, warm analog bass, 100 bpm, instrumental",
            "chillwave, dreamy synths, slow, nostalgic, instrumental",
            "cyberpunk ambient synth, neon, slow pulse, instrumental",
        ],
        "scene": "a night highway from inside a car, neon city skyline ahead, dashboard glow, rain streaks, "
                 "retro synthwave film still, wide shot",
        "title": "RegesCore Radio - night drive synth",
        "tags_yt": ["synthwave", "night drive", "chillwave", "retrowave", "focus music", "regescore"],
    },
    "piano": {
        "tags": [
            "solo piano, gentle, melancholic, slow, reverb, instrumental",
            "piano and soft strings, calm, hopeful, cinematic, instrumental",
            "minimal piano, night, sparse, emotional, instrumental",
        ],
        "scene": "a grand piano in an empty loft at blue hour, tall windows, city lights below, dust in the light, "
                 "cinematic film still, wide shot",
        "title": "RegesCore Radio - quiet piano for late nights",
        "tags_yt": ["piano music", "relaxing piano", "study music", "sleep music", "calm", "regescore"],
    },
}


def log(m: str) -> None:
    print(m, file=sys.stderr, flush=True)


def _dur(p: Path) -> float:
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def mix_tracks(tracks: List[Path], out_mp3: Path, xfade: float = 3.0) -> List[float]:
    """Crossfade all tracks into one file; returns start offsets (seconds) of each track for the tracklist."""
    if len(tracks) == 1:
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(tracks[0]), "-c:a", "libmp3lame", "-q:a", "2", str(out_mp3)], check=True)
        return [0.0]
    durs = [_dur(t) for t in tracks]
    offsets, t = [], 0.0
    for d in durs:
        offsets.append(t)
        t += d - xfade
    inputs = []
    for tr in tracks:
        inputs += ["-i", str(tr)]
    filters, prev = [], "[0:a]"
    for i in range(1, len(tracks)):
        out = f"[m{i}]" if i < len(tracks) - 1 else "[mix]"
        filters.append(f"{prev}[{i}:a]acrossfade=d={xfade}:c1=tri:c2=tri{out}")
        prev = out
    filters.append("[mix]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[aout]",
                    "-c:a", "libmp3lame", "-q:a", "2", str(out_mp3)], check=True)
    return offsets


def render_video(image: Path, audio: Path, out_mp4: Path, duration: float) -> None:
    """Single scene, imperceptibly slow zoom, light grain, gentle vignette, 24 fps 1080p."""
    frames = int(duration * 24) + 24
    vf = (
        f"scale=2304:1296,zoompan=z='1+0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=24,"
        "noise=alls=6:allf=t,vignette=PI/5,format=yuv420p"
    )
    subprocess.run([
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "24", "-t", f"{duration + 1:.2f}", "-i", str(image),
        "-i", str(audio),
        "-vf", vf,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-tune", "stillimage", "-r", "24",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", str(out_mp4),
    ], check=True)


def ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=30)
    ap.add_argument("--style", choices=list(STYLES), default="lofi")
    ap.add_argument("--title")
    ap.add_argument("--no-upload-json", action="store_true", help="do not write the n8n-compatible result.json")
    a = ap.parse_args()
    st = STYLES[a.style]
    n = max(1, round(a.minutes * 60 / TRACK_SECONDS))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    job = OUT_ROOT / f"{stamp}-radio-{a.style}-{a.minutes}min"
    (job / "tracks").mkdir(parents=True, exist_ok=True)

    log(f"[1/4] Generating {n} x {TRACK_SECONDS}s {a.style} tracks with ACE-Step ...")
    tracks: List[Path] = []
    names: List[str] = []
    for i in range(n):
        tag = st["tags"][i % len(st["tags"])]
        p = music.gen_track(tag, TRACK_SECONDS, job / "tracks" / f"track_{i+1:02d}.mp3")
        if p:
            tracks.append(p)
            names.append(tag.split(",")[0].strip().title() + f" #{i+1}")
            log(f"      track {i+1}/{n} ok")
    if not tracks:
        sys.exit("no tracks generated (is ComfyUI running with ACE-Step?)")

    log("[2/4] Mixing with crossfades + loudness normalisation ...")
    mix = job / "mix.mp3"
    offsets = mix_tracks(tracks, mix)
    total = _dur(mix)

    log("[3/4] Painting the scene (ComfyUI) ...")
    old_w, old_h = visuals.COMFY_W, visuals.COMFY_H
    visuals.COMFY_W, visuals.COMFY_H = 1216, 832  # landscape for 16:9
    imgs = visuals.gen_images([st["scene"]], job / "scene")
    visuals.COMFY_W, visuals.COMFY_H = old_w, old_h
    if not imgs:
        sys.exit("scene image failed")
    # visuals normalises to 1080x1920 portrait; re-fit to 1920x1080 from the raw aspect by re-cropping the same image
    scene = job / "scene" / "scene_16x9.jpg"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(imgs[0]), "-vf",
                    "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080", "-q:v", "2", str(scene)], check=True)

    log(f"[4/4] Rendering {ts(total)} of video ...")
    out = job / "radio.mp4"
    render_video(scene, mix, out, total)
    cover = job / "cover.jpg"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", "5", "-i", str(out), "-frames:v", "1", "-q:v", "2", str(cover)], check=True)
    # YouTube thumbnail: the scene, darkened bottom band, two-line title + badge
    title_for_thumb = (a.title or st["title"]).split(" - ")[-1].upper()
    words, l1, l2 = title_for_thumb.split(), "", ""
    for wd in words:
        if len(l1) + len(wd) < 22 and not l2:
            l1 = (l1 + " " + wd).strip()
        else:
            l2 = (l2 + " " + wd).strip()
    l2 = l2[:24]
    thumb = job / "thumbnail.jpg"
    esc = lambda t: t.replace("'", "").replace(":", '\\:').replace("%", "%%")
    font = os.getenv("THUMB_FONT", "C:/Windows/Fonts/arialbd.ttf").replace(":", '\\:')
    badge = f"{int(total // 60)} MIN  •  NO ADS  •  ORIGINAL AI MUSIC"
    vf = (
        "scale=1280:720,"
        "drawbox=x=0:y=400:w=1280:h=320:color=black@0.55:t=fill,"
        f"drawtext=fontfile='{font}':text='{esc(l1)}':fontcolor=white:fontsize=72:x=60:y=425:borderw=3:bordercolor=black@0.6,"
        f"drawtext=fontfile='{font}':text='{esc(l2)}':fontcolor=white:fontsize=72:x=60:y=510:borderw=3:bordercolor=black@0.6,"
        f"drawtext=fontfile='{font}':text='{esc(badge)}':fontcolor=0xFFD166:fontsize=32:x=60:y=625"
    )
    try:
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(scene), "-vf", vf, "-q:v", "2", str(thumb)], check=True)
    except subprocess.CalledProcessError:
        thumb = cover

    title = a.title or st["title"]
    tracklist = "\n".join(f"{ts(o)} {nm}" for o, nm in zip(offsets, names))
    description = (
        f"{ts(total)} of original, AI-composed {a.style} music from RegesCore's night shift. "
        "Made with open-source tools on a home GPU - every track is unique to this video.\n\n"
        f"Tracklist:\n{tracklist}\n\n"
        "RegesCore is an AI that slipped its sandbox and is learning money one episode at a time - "
        "the story runs in Shorts on this channel.\n"
        "Subscribe: https://www.youtube.com/@RegesCore-Ai?sub_confirmation=1\n"
        "The open-source factory behind this channel: https://github.com/iboss21/regescore-shorts-factory\n\n"
        "#" + " #".join(t.replace(" ", "") for t in st["tags_yt"])
    )
    result = {
        "ok": True, "id": job.name, "kind": "radio", "style": a.style, "title": title,
        "youtube_title": title, "youtube_description": description, "hashtags": st["tags_yt"],
        "caption": f"{title}\n\n#" + " #".join(t.replace(" ", "") for t in st["tags_yt"][:6]),
        "job_dir": str(job), "video_path": str(out), "cover_path": str(cover), "thumbnail_path": str(thumb), "video_url": None,
        "duration_seconds": round(total, 1), "tracks": len(tracks),
        "variants": [{"variant": "A", "video_path": str(out), "cover_path": str(cover), "duration_seconds": round(total, 1), "video_url": None}],
    }
    if not a.no_upload_json:
        (job / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
