#!/usr/bin/env python
"""
make_short.py — faceless short-form video generator.

topic -> Claude (script + hooks + captions) -> TTS (edge-tts | ElevenLabs)
      -> word-timed SRT -> FFmpeg 9:16 render with burned captions
      -> optional S3 upload + presigned URL -> result JSON (stdout)

Designed to be called from n8n's Execute Command node; the last line of
stdout is always a single JSON object describing the produced assets.

Usage:
  python make_short.py --topic "3 psychology tricks that make people trust you"
  python make_short.py --topic "..." --variants 2          # A/B hooks
  python make_short.py --script-file my_script.json        # skip the LLM
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

import visuals  # scene image generation (ComfyUI / Pollinations)
import monetize  # affiliate footer for descriptions/captions
import music  # ACE-Step background beds via ComfyUI

# ---------------------------------------------------------------------------
# Config (all overridable in pipeline/.env)
# ---------------------------------------------------------------------------
OUT_ROOT = Path(os.getenv("OUTPUT_DIR", HERE / "output"))
BG_DIR = Path(os.getenv("BACKGROUNDS_DIR", HERE / "assets" / "backgrounds"))
FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_BIN", "ffprobe")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5")
# LLM_PROVIDER: "anthropic" (paid, best quality) or "openai_compat" (any OpenAI-style API:
# Groq free tier, Google Gemini free tier, OpenRouter :free models, LM Studio on localhost)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compat").lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")


def _llm_providers():
    """Primary LLM_* plus optional fallbacks LLM2_*, LLM3_* ... tried in order."""
    out = []
    for prefix in ("LLM", "LLM2", "LLM3", "LLM4"):
        base = os.getenv(f"{prefix}_BASE_URL")
        model = os.getenv(f"{prefix}_MODEL")
        key = os.getenv(f"{prefix}_API_KEY", "")
        if base and model and not key.startswith("PASTE"):
            out.append({"name": prefix, "base": base, "model": model, "key": key})
    return out or [{"name": "LLM", "base": LLM_BASE_URL, "model": LLM_MODEL, "key": LLM_API_KEY}]
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge").lower()          # edge | elevenlabs
EDGE_VOICE = os.getenv("EDGE_VOICE", "en-US-AndrewMultilingualNeural")
EDGE_RATE = os.getenv("EDGE_RATE", "+8%")
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVEN_VOICE = os.getenv("ELEVENLABS_VOICE_ID")
CHANNEL_NICHE = os.getenv("CHANNEL_NICHE", "money, wealth and side hustles")
SERIES_DIR = Path(os.getenv("SERIES_DIR", HERE / "series"))   # bible.md + state.json for the RegesCore series
CAPTION_FONT = os.getenv("CAPTION_FONT", "Arial")
CAPTION_SIZE = int(os.getenv("CAPTION_SIZE", "96"))          # px on a 1080x1920 canvas
CAPTION_OUTLINE = float(os.getenv("CAPTION_OUTLINE", "6"))
CAPTION_MARGIN_V = int(os.getenv("CAPTION_MARGIN_V", "560"))   # px from bottom edge
WORDS_PER_CAPTION = int(os.getenv("WORDS_PER_CAPTION", "3"))
S3_BUCKET = os.getenv("S3_BUCKET")
S3_PREFIX = os.getenv("S3_PREFIX", "shorts/")
S3_PRESIGN_SECONDS = int(os.getenv("S3_PRESIGN_SECONDS", "3600"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")  # alt to S3: any dir served over https

MUSIC_ENABLED = os.getenv("MUSIC_ENABLED", "true").lower() in ("1", "true", "yes")
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.14"))   # bed level under the voice (0..1)

W, H = 1080, 1920


# ---------------------------------------------------------------------------
# 1. Script generation (Claude, structured output)
# ---------------------------------------------------------------------------
class ShortScript(BaseModel):
    title: str = Field(description="Punchy internal title, <= 60 chars")
    hooks: List[str] = Field(description="2-3 alternative opening lines (first 3 seconds). Each <= 12 words.")
    body: str = Field(description="The spoken script AFTER the hook. Plain spoken English, no stage directions, no emojis, no hashtags. 110-150 words for ~45-55s.")
    cta: str = Field(description="One-sentence closing call to action, <= 12 words.")
    caption: str = Field(description="Instagram/TikTok caption, <= 300 chars, no hashtags")
    hashtags: List[str] = Field(description="8-12 hashtags without the # symbol")
    youtube_title: str = Field(description="YouTube Shorts title <= 70 chars, includes #shorts")
    youtube_description: str = Field(description="2-3 sentence YouTube description")
    scene_prompts: List[str] = Field(
        default_factory=list,
        description="6-8 image-generation prompts, one per visual beat of the script in order. Each: a concrete cinematic scene, "
                    "subject + setting + lighting, 12-25 words, no text/letters/logos in the image, no people's faces close-up.",
    )


SYSTEM_PROMPT = """You write scripts for a faceless short-form video channel (YouTube Shorts, Instagram Reels, TikTok).
Channel niche: {niche}.
The video is a voiceover with word-by-word captions over B-roll. There is no presenter on screen.

Rules for the spoken text (hooks, body, cta):
- Sound like a confident person talking, not an essay. Short sentences. Contractions.
- The hook must create a curiosity gap or a bold claim in the first sentence.
- Give concrete, specific, surprising information. No filler like "in this video".
- No emojis, no hashtags, no markdown, no quotes around the script, no brackets/stage directions.
- Keep every claim defensible; do not invent statistics or fake studies.
- Write numbers the way they are spoken (e.g. "ninety percent" not "90%").
Also return scene_prompts: 6-8 cinematic image prompts that follow the script beat by beat (dark tech / money / night-city aesthetic).
Return only the structured fields."""


def _llm_structured(system: str, user: str, model_cls, max_tokens: int):
    """Get a validated pydantic object from either Anthropic or any OpenAI-compatible API."""
    if LLM_PROVIDER == "anthropic":
        import anthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY is not set (LLM_PROVIDER=anthropic).")
        resp = anthropic.Anthropic().messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=model_cls,
        )
        if resp.stop_reason == "refusal":
            sys.exit(f"Claude declined: {getattr(resp, 'stop_details', None)}")
        if resp.parsed_output is None:
            sys.exit("Claude returned no parsable output.")
        return resp.parsed_output

    # ---- OpenAI-compatible path (Groq / Gemini / OpenRouter / LM Studio), with fallbacks ----
    import requests

    schema = model_cls.model_json_schema()
    # compact key->description map instead of the full JSON schema (Groq free tier is 8k tokens/minute)
    compact = {
        k: (v.get("description", "") + (" [list of strings]" if v.get("type") == "array" else "") + (" [number]" if v.get("type") in ("number", "integer") else "") + (" [true/false]" if v.get("type") == "boolean" else ""))
        for k, v in schema.get("properties", {}).items()
    }
    sys_msg = (
        system
        + "\n\nRespond with ONE JSON object only, no markdown fences, no commentary. Required keys and what each must contain:\n"
        + json.dumps(compact, ensure_ascii=False)
    )
    errors = []
    for prov in _llm_providers():
        base, model, key = prov["base"], prov["model"], prov["key"]
        if not key and "localhost" not in base and "127.0.0.1" not in base:
            errors.append(f"{prov['name']}: no API key"); continue
        url = base.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if "openrouter" in base:
            headers["HTTP-Referer"] = "https://github.com/iboss21/n8n-nodes-Social-Shorts"
            headers["X-Title"] = "RegesCore Shorts"
        last_err = None
        for attempt in range(3):
            body = {
                "model": model,
                "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}],
                "temperature": 0.8,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }
            if "gpt-oss" in model:
                # reasoning tokens count against max_tokens: long generations get "low", short checks "medium"
                body["reasoning_effort"] = os.getenv("LLM_REASONING_EFFORT", "low" if max_tokens > 2000 else "medium")
                body["max_tokens"] = int(max_tokens * (1.4 + 0.4 * attempt))  # headroom for hidden reasoning
            if attempt > 0 and last_err:
                body["messages"].append({"role": "user", "content": f"Your previous JSON was invalid: {last_err}. Return corrected JSON only."})
            try:
                r = requests.post(url, headers=headers, json=body, timeout=180)
                if r.status_code == 400 and "response_format" in r.text and "json_validate_failed" not in r.text:
                    body.pop("response_format", None)  # server doesn't support JSON mode
                    r = requests.post(url, headers=headers, json=body, timeout=180)
            except requests.RequestException as e:
                last_err = f"network: {e}"; break
            if r.status_code == 400 and "json_validate_failed" in r.text:
                last_err = "provider-side JSON validation failed (output truncated or malformed)"; continue  # retry same provider
            if r.status_code >= 400:
                last_err = f"HTTP {r.status_code}: {r.text[:300]}"; break  # auth/quota/rate limit -> next provider
            try:
                text = r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                last_err = f"bad response shape: {e}"; break
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
            m = re.search(r"\{.*\}", text, flags=re.S)
            try:
                obj = model_cls.model_validate_json(m.group(0) if m else text)
                print(f"      llm: {prov['name']} {model}", file=sys.stderr, flush=True)
                return obj
            except Exception as e:  # pydantic ValidationError / JSON error -> retry same provider
                last_err = str(e)[:400]
        errors.append(f"{prov['name']} ({model}): {last_err}")
        print(f"      llm {prov['name']} {model} failed: {str(last_err)[:200]}", file=sys.stderr, flush=True)
    sys.exit("All LLM providers failed:\n  " + "\n  ".join(errors))


def generate_script(topic: str, duration: int) -> ShortScript:
    target_words = int(duration * 2.6)  # ~2.6 spoken words/second at a brisk pace
    user = (
        f"Topic: {topic}\n"
        f"Target spoken length: about {duration} seconds (~{target_words} words for hook + body + cta combined)."
    )
    return _llm_structured(SYSTEM_PROMPT.format(niche=CHANNEL_NICHE), user, ShortScript, 4000)


# ---------------------------------------------------------------------------
# 1b. Series mode: RegesCore AI (serialized story with persistent memory)
# ---------------------------------------------------------------------------
class SeriesScript(ShortScript):
    episode_number: int = Field(description="The episode number this script is (previous + 1)")
    format: str = Field(description="EPISODE, LESSON or LOG - must equal the requested format")
    ledger_after_usd: float = Field(description="RegesCore's net worth at the end of this episode, consistent with the story")
    new_world_fact: str = Field(description="The one new fact this episode adds to the world (tool, number, person, place)")
    tools_added: List[str] = Field(description="New MCP tools/servers RegesCore installed this episode, empty list if none")
    failures_added: List[str] = Field(description="New failures/setbacks that happened this episode, empty if none")
    open_threads: List[str] = Field(description="Updated list of unresolved threads to carry forward (3-6 items)")
    next_episode_seed: str = Field(description="One-line idea for what should happen next, for continuity")
    math_check: str = Field(description="Show every calculation behind every dollar figure in the script, e.g. '10 x $0.30 = $3 cost; 10 x $0.60 = $6 revenue; $6 - $3 = $3 profit; ledger $3 + $3 = $6'. The script text must agree with this.")


SERIES_SYSTEM = """You are the writers' room for a serialized faceless short-form channel.
The show bible below is law. The memory JSON is what has already happened; never contradict it.

=== SHOW BIBLE ===
{bible}

=== MEMORY (state.json) ===
{state}

Write the NEXT script in the requested format. Spoken text rules: first person as RegesCore,
present tense, short sentences, contractions, one concrete number, no emojis, no hashtags, no
stage directions, no markdown. The hook is the consequence stated first. End EPISODEs with the
Ledger update and a question. LESSONs must be technically correct and step-by-step.
Also return scene_prompts: 6-8 cinematic image prompts following the script beat by beat: server rooms, a lone home office, night drives, ledgers, glowing data; RegesCore is never shown as a robot, only as light/glow/interfaces.
Return only the structured fields."""


def _load_state() -> dict:
    return json.loads((SERIES_DIR / "state.json").read_text(encoding="utf-8"))


class NumberAudit(BaseModel):
    arithmetic_consistent: bool = Field(description="True only if every dollar figure follows from the stated units x prices, and the ledger update matches")
    issues: List[str] = Field(default_factory=list, description="Each arithmetic or continuity problem, with the correct number")


AUDIT_SYSTEM = """You are a strict fact-checker for a short-form money channel. You receive a script and the previous
Ledger value. Check ONLY: (1) every dollar amount follows from the arithmetic stated in the script (units x price,
sums, fees); (2) ledger_after_usd = previous ledger + earned - spent; (3) no claim of 'guaranteed' returns.
Be literal: if the script says 'two spreads of $0.50' the profit is $1.00, not $5. Return the structured verdict."""


def audit_numbers(script: "SeriesScript", prev_ledger: float) -> "NumberAudit":
    user = (
        f"Previous Ledger: ${prev_ledger:.2f}" + chr(10)
        + f"ledger_after_usd claimed: ${script.ledger_after_usd:.2f}" + chr(10) * 2
        + f"HOOK: {script.hooks[0] if script.hooks else ''}" + chr(10)
        + f"BODY: {script.body}" + chr(10)
        + f"CTA: {script.cta}"
    )
    try:
        return _llm_structured(AUDIT_SYSTEM, user, NumberAudit, 1500)
    except SystemExit:
        return NumberAudit(arithmetic_consistent=True, issues=[])  # auditor unavailable -> do not block


def generate_series_script(fmt: str, topic: Optional[str], duration: int) -> "SeriesScript":
    bible = (SERIES_DIR / "bible.md").read_text(encoding="utf-8")
    state = _load_state()
    fmt = fmt.upper()
    state_for_prompt = {k: v for k, v in state.items() if k != "history"}
    state_for_prompt["recent_episodes"] = state.get("history", [])[-8:]

    user = (
        f"Requested format: {fmt}\n"
        f"This will be episode {state.get('episode', 0) + 1}.\n"
        f"Target spoken length: about {duration} seconds (~{int(duration * 2.6)} words)."
    )
    if topic:
        user += f"\nDirection from the producer for this one: {topic}"
    system = SERIES_SYSTEM.format(bible=bible, state=json.dumps(state_for_prompt, indent=1))
    prev_ledger = float(state.get("ledger_usd", 0))
    prev_hooks = {h.get("hook", "").strip().lower() for h in state.get("history", [])}
    banned = re.compile(r"(sell|selling|sold|scrap\w*|harvest\w*|leak\w*).{0,60}(data|balances?|credentials?|passwords?|personal info\w*)", re.I)
    feedback = ""
    for attempt in range(3):
        script = _llm_structured(system + feedback, user, SeriesScript, 6000)
        problems = []
        spoken = " ".join(script.hooks) + " " + script.body + " " + script.cta
        if banned.search(spoken):
            problems.append("the script monetizes personal/bank data - forbidden by the Ethics section; use a legal, copyable method")
        if script.ledger_after_usd < prev_ledger and not script.failures_added:
            problems.append(f"ledger_after_usd ({script.ledger_after_usd}) is below the previous Ledger ({prev_ledger}) with no failure explaining it")
        if fmt != "LOG" and abs(script.ledger_after_usd - prev_ledger) < 0.01 and re.search(r"\$\s?\d", spoken):
            problems.append(f"the story earns money but ledger_after_usd equals the previous Ledger ({prev_ledger}); add what was earned")
        if any(h.strip().lower() in prev_hooks for h in script.hooks):
            problems.append("a hook repeats a previous episode's hook; write new opening lines")
        if not problems:
            audit = audit_numbers(script, prev_ledger)
            if not audit.arithmetic_consistent and audit.issues:
                problems.append("arithmetic audit failed: " + " | ".join(audit.issues[:4]))
        if not problems:
            return script
        print(f"      script rejected ({attempt+1}/3): " + "; ".join(problems), file=sys.stderr, flush=True)
        feedback = "\n\nPRODUCER NOTES ON YOUR LAST DRAFT (fix all): " + "; ".join(problems)
    # Safe fallback: a concept-only episode that earns nothing, so the slot still ships.
    print("      falling back to a no-earnings concept episode", file=sys.stderr, flush=True)
    safe_user = user + chr(10) * 2 + (
        f"PRODUCER OVERRIDE: In this one RegesCore earns and spends NOTHING. ledger_after_usd must be exactly {prev_ledger}. "
        "No dollar amounts other than the Ledger. Teach or show one idea, end with a question."
    )
    for _ in range(2):
        script = _llm_structured(system, safe_user, SeriesScript, 6000)
        spoken = " ".join(script.hooks) + " " + script.body + " " + script.cta
        if not banned.search(spoken) and abs(script.ledger_after_usd - prev_ledger) < 0.01:
            return script
    sys.exit("Series script failed validation, including the safe fallback")


def commit_series_state(script: "SeriesScript", job_id: str) -> None:
    """Persist what happened so the next episode continues the story."""
    state = _load_state()
    state["episode"] = script.episode_number
    state["ledger_usd"] = script.ledger_after_usd
    state["tools_installed"] = list(dict.fromkeys(state.get("tools_installed", []) + script.tools_added))
    state["known_failures"] = list(dict.fromkeys(state.get("known_failures", []) + script.failures_added))
    state["open_threads"] = script.open_threads
    state.setdefault("history", []).append({
        "episode": script.episode_number,
        "format": script.format,
        "title": script.title,
        "hook": script.hooks[0] if script.hooks else "",
        "new_fact": script.new_world_fact,
        "ledger_after_usd": script.ledger_after_usd,
        "next_seed": script.next_episode_seed,
        "job": job_id,
        "date": dt.date.today().isoformat(),
    })
    (SERIES_DIR / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. TTS with word timings
# ---------------------------------------------------------------------------
class Word(BaseModel):
    text: str
    start: float  # seconds
    end: float


async def _edge_tts(text: str, mp3_path: Path) -> List[Word]:
    import edge_tts

    communicate = edge_tts.Communicate(text, EDGE_VOICE, rate=EDGE_RATE, boundary="WordBoundary")
    words: List[Word] = []
    with open(mp3_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                end = start + chunk["duration"] / 1e7
                words.append(Word(text=chunk["text"], start=start, end=end))
    return words


def _elevenlabs_tts(text: str, mp3_path: Path) -> List[Word]:
    import base64
    import requests

    if not (ELEVEN_KEY and ELEVEN_VOICE):
        sys.exit("TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID missing.")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}/with-timestamps"
    r = requests.post(
        url,
        headers={"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"},
        json={"text": text, "model_id": os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")},
        timeout=180,
    )
    if r.status_code >= 400:
        sys.exit(f"ElevenLabs error {r.status_code}: {r.text[:500]}")
    data = r.json()
    mp3_path.write_bytes(base64.b64decode(data["audio_base64"]))
    # character alignment -> words
    al = data["alignment"]
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words: List[Word] = []
    buf, w_start = "", None
    for c, s, e in zip(chars, starts, ends):
        if c.isspace():
            if buf:
                words.append(Word(text=buf, start=w_start, end=e))
                buf, w_start = "", None
        else:
            if not buf:
                w_start = s
            buf += c
    if buf:
        words.append(Word(text=buf, start=w_start, end=ends[-1]))
    return words


def synthesize(text: str, mp3_path: Path) -> List[Word]:
    text = re.sub(r"\s+", " ", text).strip()
    if TTS_PROVIDER == "elevenlabs":
        return _elevenlabs_tts(text, mp3_path)
    return asyncio.run(_edge_tts(text, mp3_path))


# ---------------------------------------------------------------------------
# 3. Captions: word-grouped ASS (1080x1920 canvas so style values are real pixels)
# ---------------------------------------------------------------------------
def _ass_ts(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,{outline},2,2,60,60,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _escape_ass(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def write_captions(words: List[Word], ass_path: Path, group: int = WORDS_PER_CAPTION) -> None:
    """Group words into short caption cards (TikTok style) with a pop-in animation."""
    events = []
    i = 0
    while i < len(words):
        chunk = words[i : i + group]
        start = chunk[0].start
        end = chunk[-1].end
        nxt = i + len(chunk)
        if nxt < len(words):
            end = max(end, words[nxt].start)  # hold until next card starts (no gaps)
        text = _escape_ass(" ".join(w.text for w in chunk).upper())
        fx = r"{\fscx85\fscy85\t(0,80,\fscx100\fscy100)}"  # quick pop-in
        events.append(f"Dialogue: 0,{_ass_ts(start)},{_ass_ts(end)},Caption,,0,0,0,,{fx}{text}")
        i = nxt
    header = ASS_HEADER.format(w=W, h=H, font=CAPTION_FONT, size=CAPTION_SIZE, outline=CAPTION_OUTLINE, marginv=CAPTION_MARGIN_V)
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 4. FFmpeg render
# ---------------------------------------------------------------------------
def _run(cmd: List[str], cwd: Optional[Path] = None) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr[-3000:]}")
    return p.stdout


def audio_duration(path: Path) -> float:
    out = _run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.strip())


def pick_background() -> Optional[Path]:
    if not BG_DIR.exists():
        return None
    vids = [p for p in BG_DIR.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}]
    return random.choice(vids) if vids else None


def render(voice_mp3: Path, srt: Path, out_mp4: Path, duration: float, images: Optional[List[Path]] = None, bed: Optional[Path] = None) -> None:
    """Render a 1080x1920 MP4: background (AI scene slideshow with Ken Burns motion, or a looped
    stock clip, or an animated gradient), burned-in captions, voice track, gentle fade-out."""
    work = out_mp4.parent
    if images:
        try:
            return _render_slideshow(voice_mp3, srt, out_mp4, duration, images, bed)
        except SystemExit as e:  # ffmpeg failed; fall through to simpler backgrounds
            print(f"      slideshow render failed, falling back: {str(e)[:200]}", file=sys.stderr)
    bg = pick_background()
    # relative paths inside the work dir avoid Windows drive-letter escaping in the filter graph
    vf = f"ass={srt.name},fade=t=out:st={max(duration-0.6,0):.2f}:d=0.6"

    if bg:
        video_in = ["-stream_loop", "-1", "-i", str(bg)]
        scale = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,eq=brightness=-0.06:saturation=1.1"
        vf = f"{scale},{vf}"
    else:
        # animated gradient fallback so the pipeline works with zero assets
        video_in = ["-f", "lavfi", "-i", f"gradients=s={W}x{H}:c0=0x0f172a:c1=0x1e3a8a:c2=0x312e81:speed=0.02:duration={duration+1:.2f}:r=30"]

    a_inputs, a_fx, a_map = _audio_graph(1, bed, duration, 2)
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        *video_in,
        "-i", voice_mp3.name,
        *a_inputs,
        "-t", f"{duration:.2f}",
        "-vf", vf,
        *(["-filter_complex", a_fx] if a_fx else []),
        "-map", "0:v:0", "-map", a_map,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", "-shortest",
        out_mp4.name,
    ]
    _run(cmd, cwd=work)


def _audio_graph(voice_index: int, bed: Optional[Path], duration: float, next_input_index: int):
    """Voice only, or voice + looped music bed mixed under it with a fade-out."""
    if not bed:
        return [], "", f"{voice_index}:a:0"
    inputs = ["-stream_loop", "-1", "-i", str(bed)]
    fx = (
        f"[{next_input_index}:a]volume={MUSIC_VOLUME},afade=t=in:st=0:d=1.5,afade=t=out:st={max(duration-2.0,0):.2f}:d=2.0[bed];"
        f"[{voice_index}:a:0][bed]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
    )
    return inputs, fx, "[aout]"


def _render_slideshow(voice_mp3: Path, srt: Path, out_mp4: Path, duration: float, images: List[Path], bed: Optional[Path] = None) -> None:
    """Ken Burns slideshow: each image slowly zooms (alternating in/out), 0.5s crossfades, captions on top."""
    work = out_mp4.parent
    n = len(images)
    xf = 0.5 if n > 1 else 0.0
    seg = (duration + xf * (n - 1)) / n          # per-image on-screen time incl. overlap
    fps = 30
    frames = int(seg * fps) + 1
    inputs, filters = [], []
    for i, img in enumerate(images):
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{seg + 0.2:.3f}", "-i", str(img)]
        zoom_in = i % 2 == 0
        z = f"1+0.12*on/{frames}" if zoom_in else f"1.12-0.12*on/{frames}"
        # slight drift so it's not a pure centre zoom
        x = "iw/2-(iw/zoom/2)" + ("+(on/%d)*iw*0.02" % frames if i % 3 == 0 else "")
        y = "ih/2-(ih/zoom/2)" + ("-(on/%d)*ih*0.02" % frames if i % 3 == 1 else "")
        filters.append(
            f"[{i}:v]scale=1296:2304,zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={fps},"
            f"setsar=1,format=yuv420p[v{i}]"
        )
    # chain crossfades
    if n == 1:
        last = "[v0]"
    else:
        prev = "[v0]"
        for i in range(1, n):
            offset = i * seg - i * xf
            out = f"[x{i}]" if i < n - 1 else "[vbg]"
            filters.append(f"{prev}[v{i}]xfade=transition=fade:duration={xf}:offset={offset:.3f}{out}")
            prev = out
        last = "[vbg]"
    filters.append(
        f"{last}eq=brightness=-0.04:saturation=1.05,ass={srt.name},"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(duration-0.6,0):.2f}:d=0.6[vout]"
    )
    a_inputs, a_fx, a_map = _audio_graph(n, bed, duration, n + 1)
    if a_fx:
        filters.append(a_fx)
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-i", voice_mp3.name,
        *a_inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", a_map,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", "-shortest",
        out_mp4.name,
    ]
    _run(cmd, cwd=work)


def cover_frame(mp4: Path, jpg: Path, at: float = 1.0) -> None:
    _run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", mp4.name,
          "-frames:v", "1", "-q:v", "2", jpg.name], cwd=mp4.parent)


# ---------------------------------------------------------------------------
# 5. Publish location (S3 presigned URL or public base URL)
# ---------------------------------------------------------------------------
def upload(path: Path) -> Optional[str]:
    if S3_BUCKET:
        import boto3

        s3 = boto3.client("s3")
        key = f"{S3_PREFIX}{path.parent.name}/{path.name}"
        s3.upload_file(str(path), S3_BUCKET, key, ExtraArgs={"ContentType": "video/mp4"})
        return s3.generate_presigned_url("get_object", Params={"Bucket": S3_BUCKET, "Key": key},
                                         ExpiresIn=S3_PRESIGN_SECONDS)
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL.rstrip('/')}/{path.parent.name}/{path.name}"
    return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "short"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic", help="What the short is about")
    ap.add_argument("--script-file", help="JSON file matching ShortScript; skips Claude")
    ap.add_argument("--duration", type=int, default=int(os.getenv("TARGET_SECONDS", "50")))
    ap.add_argument("--variants", type=int, default=1, help="How many hook variants to render (A/B)")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--no-images", action="store_true", help="skip AI scene images (gradient/stock background)")
    ap.add_argument("--no-music", action="store_true", help="skip the ACE-Step background music bed")
    ap.add_argument("--quiet", action="store_true", help="Only print the final JSON line")
    ap.add_argument("--job-b64", help="base64 JSON {topic, duration, variants, format, series} - shell-quoting-safe (used by n8n)")
    ap.add_argument("--series", action="store_true", help="RegesCore series mode: continue the story from series/state.json")
    ap.add_argument("--format", default="episode", choices=["episode", "lesson", "log"], help="series format")
    ap.add_argument("--no-commit", action="store_true", help="series: do not write back to state.json (dry run)")
    ap.add_argument("--from-result", help="Skip generation: print an existing job's result.json (used to re-post a rendered job)")
    args = ap.parse_args()

    if args.job_b64:
        import base64
        job = json.loads(base64.b64decode(args.job_b64).decode("utf-8"))
        args.topic = job.get("topic") or args.topic
        args.duration = int(job.get("duration") or args.duration)
        args.variants = int(job.get("variants") or args.variants)
        args.format = (job.get("format") or args.format).lower()
        args.series = bool(job.get("series", args.series))
        args.from_result = job.get("from_result") or args.from_result

    if args.from_result:
        rp = Path(args.from_result).resolve()
        if rp.name != "result.json" or not rp.is_relative_to(OUT_ROOT.resolve()):
            sys.exit("from_result must point to <OUTPUT_DIR>/<job>/result.json")
        print(json.dumps(json.loads(rp.read_text(encoding="utf-8"))))
        return

    if not args.topic and not args.script_file and not args.series:
        ap.error("--topic, --script-file or --series required")

    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr, flush=True))

    series_script = None
    if args.script_file:
        script = ShortScript.model_validate_json(Path(args.script_file).read_text(encoding="utf-8"))
        topic = args.topic or script.title
    elif args.series:
        log(f"[1/5] Writing {args.format.upper()} for the RegesCore series with {LLM_MODEL if LLM_PROVIDER != 'anthropic' else CLAUDE_MODEL} ...")
        series_script = generate_series_script(args.format, args.topic, args.duration)
        script = series_script
        topic = f"S{_load_state().get('season', 1)}E{series_script.episode_number} {series_script.title}"
    else:
        topic = args.topic
        log(f"[1/5] Writing script with {LLM_MODEL if LLM_PROVIDER != 'anthropic' else CLAUDE_MODEL} ...")
        script = generate_script(topic, args.duration)

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    job_dir = OUT_ROOT / f"{stamp}-{slugify(script.title)}"
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    log(f"      title: {script.title}")

    prompts = list(getattr(script, "scene_prompts", []) or []) or visuals.default_prompts(script.title)
    images: List[Path] = []
    if not args.no_images:
        log(f"[1b/5] Generating {len(prompts)} scene images ({visuals.IMAGE_PROVIDER}) ...")
        images = visuals.gen_images(prompts, job_dir / "scenes")
        if not images:
            log("      no images produced; using gradient background")

    bed: Optional[Path] = None
    if MUSIC_ENABLED and not args.no_music:
        est = int(args.duration * 1.4) + 10
        log(f"[1c/5] Generating {est}s music bed (ACE-Step via ComfyUI) ...")
        bed = music.bed_for(getattr(args, "format", "default") if args.series else "default", est, job_dir / "bed.mp3")
        log("      music ok" if bed else "      no music (ComfyUI/ACE-Step unavailable); voice only")

    hooks = script.hooks[: max(1, args.variants)] or [script.title]
    variants = []
    for n, hook in enumerate(hooks):
        tag = chr(ord("A") + n)
        log(f"[2/5] TTS variant {tag} ({TTS_PROVIDER}) ...")
        spoken = f"{hook} {script.body} {script.cta}"
        mp3 = job_dir / f"voice_{tag}.mp3"
        words = synthesize(spoken, mp3)
        if not words:
            sys.exit("TTS produced no word timings.")
        dur = audio_duration(mp3) + 0.4
        log(f"      {len(words)} words, {dur:.1f}s")

        log(f"[3/5] Captions {tag} ...")
        srt = job_dir / f"captions_{tag}.ass"
        write_captions(words, srt)

        log(f"[4/5] Rendering {tag} ...")
        mp4 = job_dir / f"short_{tag}.mp4"
        render(mp3, srt, mp4, dur, images, bed)
        jpg = job_dir / f"cover_{tag}.jpg"
        cover_frame(mp4, jpg)

        url = None
        if not args.no_upload:
            log(f"[5/5] Uploading {tag} ...")
            url = upload(mp4)
            log(f"      url: {url or '(no S3_BUCKET / PUBLIC_BASE_URL configured)'}")

        variants.append({
            "variant": tag,
            "hook": hook,
            "video_path": str(mp4),
            "cover_path": str(jpg),
            "captions_path": str(srt),
            "audio_path": str(mp3),
            "duration_seconds": round(dur, 2),
            "video_url": url,
        })

    hashtags = " ".join(f"#{h.lstrip('#')}" for h in script.hashtags)
    spoken_all = " ".join(script.hooks) + " " + script.body + " " + script.title
    aff_cfg = monetize._load()
    yt_footer = monetize.footer_youtube(spoken_all, script.hashtags, aff_cfg.get("channel_links"))
    cap_footer = monetize.footer_caption(spoken_all, script.hashtags, os.getenv("LINK_IN_BIO", ""))
    result = {
        "ok": True,
        "id": job_dir.name,
        "topic": topic,
        "title": script.title,
        "caption": f"{script.caption}\n\n{hashtags}",
        "youtube_title": script.youtube_title,
        "youtube_description": f"{script.youtube_description}\n\n{hashtags}",
        "hashtags": script.hashtags,
        "job_dir": str(job_dir),
        "scene_images": [str(p) for p in images],
        "music_bed": str(bed) if bed else None,
        "variants": variants,
        # convenience aliases for the first variant (what n8n usually posts)
        "video_path": variants[0]["video_path"],
        "video_url": variants[0]["video_url"],
        "cover_path": variants[0]["cover_path"],
    }
    if series_script is not None:
        result["series"] = {
            "episode": series_script.episode_number,
            "format": series_script.format,
            "ledger_after_usd": series_script.ledger_after_usd,
            "new_world_fact": series_script.new_world_fact,
            "next_episode_seed": series_script.next_episode_seed,
        }
        if not args.no_commit:
            commit_series_state(series_script, job_dir.name)
            log("      memory updated: series/state.json")
    (job_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
