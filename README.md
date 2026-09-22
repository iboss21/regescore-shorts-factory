# RegesCore Shorts Factory

A **$0/month faceless short-form video business** in one repo. A serialized story — *RegesCore*, an AI that slipped its sandbox and is teaching itself money at AGI speed — written, voiced, illustrated, rendered and published to **YouTube Shorts, Instagram Reels and TikTok** automatically.

First episode: https://www.youtube.com/@RegesCore-Ai

```
story memory ─► free LLM writes next beat ─► free TTS ─► AI scene images (local ComfyUI)
             ─► FFmpeg 9:16 render (Ken Burns + word captions, A/B hooks)
             ─► n8n: YouTube upload · Instagram Reels · TikTok · Discord report
```

Everything runs on a normal Windows PC. No paid APIs required.

## Stack (all free)

| Layer | Default | Alternatives (env switch) |
|---|---|---|
| Script | Groq `openai/gpt-oss-120b` (free tier) | OpenRouter `:free` models, Gemini free tier, LM Studio (offline), Anthropic (paid, best) — auto-fallback chain |
| Voice | `edge-tts` Microsoft neural voices | ElevenLabs |
| Images | **ComfyUI** on your GPU (Juggernaut-XL) | Pollinations (hosted FLUX, no key), none (gradient) |
| Music | **ACE-Step** inside ComfyUI (original tracks, ~18 s per minute of audio) | off |
| Render | FFmpeg | — |
| Orchestration | n8n community edition (local) | Docker/VPS later |
| Hosting for IG URL | S3 presigned | any https folder |

## Layout

| Path | What |
|---|---|
| `pipeline/make_short.py` | The factory. `--series` continues the story; `--topic` makes a one-off; `--script-file` renders a fixed script. |
| `pipeline/visuals.py` | Scene image generation (ComfyUI API / Pollinations). |
| `pipeline/music.py` | Original music via ACE-Step inside ComfyUI: background beds for shorts, full tracks for radio. |
| `pipeline/make_lofi.py` | Long-form 'RegesCore Radio' videos (30-60 min lofi/ambient/synth/piano) for the 4,000-watch-hour route. Weekly slot in the workflow. |
| `pipeline/monetize.py` + `affiliates.json` | Affiliate/tool links matched to each episode, appended to descriptions. |
| `BUSINESS.md` | Revenue plan, weekly loop, Gumroad listing copy. |
| `pipeline/series/bible.md` | The show bible: premise, voice, formats (EPISODE / LESSON / LOG), number rules, hard limits. **Edit this to steer the show.** |
| `pipeline/series/state.json` | Story memory: episode counter, Ledger, tools installed, history. Updated after every render. |
| `pipeline/.env.example` | All settings. Copy to `.env`, add your keys. |
| `workflows/faceless_shorts_pipeline.json` | n8n workflow: daily schedule / webhook / manual → render → YouTube + IG + TikTok → Discord. |
| `n8n-node/` | Community node package: **Instagram Reels Publisher** and **TikTok Post** (Content Posting API, binary or URL). |
| `discord-to-n8n-worker/` | Cloudflare Worker: Discord slash command → n8n webhook. |
| `start-n8n.ps1` | Starts n8n with the flags n8n 2.x needs (Execute Command, `$env`, file access). |

## Quick start

```powershell
# 1. deps
pip install -r pipeline/requirements.txt
npm i -g n8n
cd n8n-node; npm i; npm run build; cd ..
mkdir $HOME\.n8n\custom\n8n-nodes-social-shorts; copy n8n-node\dist,n8n-node\package.json $HOME\.n8n\custom\n8n-nodes-social-shorts -Recurse

# 2. keys
copy pipeline\.env.example pipeline\.env      # add a free Groq key (console.groq.com) — that is enough to start

# 3. make one video
python pipeline\make_short.py --series --format episode --variants 2 --no-upload

# 4. run n8n, import the workflow, connect YouTube OAuth, activate
.\start-n8n.ps1
n8n import:workflow --input=workflows/faceless_shorts_pipeline.json
```

Trigger a post manually:

```bash
curl -X POST http://localhost:5678/webhook/shortform -H "Content-Type: application/json" -d '{"format":"lesson","platforms":{"yt":true,"ig":false,"tiktok":false}}'
```

Re-post an already rendered job: `{"from_result": "<path>/result.json"}`.

## Platform setup

- **YouTube** — Google Cloud project → enable *YouTube Data API v3* → OAuth client (web) with redirect `http://localhost:5678/rest/oauth2-credential/callback` → add yourself as test user → n8n credential *YouTube OAuth2 API* → sign in choosing the **brand channel**.
- **Instagram** — IG Business/Creator account linked to a Facebook Page; Meta app (Live) with `instagram_content_publish`; long-lived user token → `IG_USER_ID`, `IG_ACCESS_TOKEN`. Needs a public MP4 URL → set `S3_BUCKET` or `PUBLIC_BASE_URL`.
- **TikTok** — developers.tiktok.com app with *Content Posting API* + *Login Kit*, scopes `video.upload video.publish` → `TIKTOK_ACCESS_TOKEN`. Unaudited apps can only post **SELF_ONLY** (private); after audit set `TIKTOK_PRIVACY=PUBLIC_TO_EVERYONE`.

## Quality guard

Free models sometimes get arithmetic wrong. The bible has a "Numbers must be real" section, and every render writes `script.json` next to the video — read it before posting, or run with `platforms` off and post via `from_result` after review.

## Fixes vs. the original `n8n-nodes-social-shorts`

Node classes renamed to match filenames (n8n crashed on load), `n8n` block added to `package.json`, `skipLibCheck`, icon copy step, and TikTok implemented (was a stub).

MIT © iBoss
