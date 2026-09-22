# AI Shorts Factory — buyer setup guide (30 minutes, $0/month)

You bought the exact system behind youtube.com/@RegesCore-Ai. This guide gets you from zero to your first
auto-posted video. Windows steps shown; Mac/Linux are the same commands without `.ps1`.

## 0. What you need
- A PC. A GPU (8 GB+) makes images/music local and free; without one, images use the free hosted Pollinations API and music is skipped.
- Free accounts: Google (YouTube), Groq (console.groq.com — free API key), GitHub (optional).
- Installed: Python 3.12+, Node 20+, FFmpeg (`winget install Gyan.FFmpeg`), optionally ComfyUI.

## 1. Install
```powershell
git clone https://github.com/iboss21/regescore-shorts-factory.git
cd regescore-shorts-factory
pip install -r pipeline/requirements.txt
npm i -g n8n
cd n8n-node; npm i; npm run build; cd ..
mkdir "$HOME\.n8n\custom\n8n-nodes-social-shorts" -Force
Copy-Item n8n-node\dist "$HOME\.n8n\custom\n8n-nodes-social-shorts\dist" -Recurse
Copy-Item n8n-node\package.json "$HOME\.n8n\custom\n8n-nodes-social-shorts\"
copy pipeline\.env.example pipeline\.env
```
Open `pipeline/.env` and paste your Groq key into `LLM_API_KEY`. That is the only key required to start.

## 2. Make your show yours (10 minutes)
- `pipeline/series/bible.md` — replace RegesCore with your character, niche and rules. Keep the *Numbers must be real* and *Ethics* sections.
- `pipeline/series/state.json` — reset `episode` to 0, `ledger_usd` to 0, `history` to `[]`.
- `pipeline/.env` — `EDGE_VOICE` (run `edge-tts --list-voices`), `IMAGE_STYLE`, `CAPTION_*`.
- `pipeline/affiliates.json` — your affiliate links; placeholders are skipped automatically.

## 3. First video (no posting)
```powershell
python pipeline\make_short.py --series --format episode --variants 2 --no-upload
```
Open `pipeline/output/<job>/short_A.mp4`. Read `script.json`. Iterate on the bible until you like it.

## 4. Connect YouTube
1. console.cloud.google.com → new project → enable **YouTube Data API v3**.
2. Google Auth Platform → configure (External, Testing) → add your Gmail as a test user.
3. Clients → create **Web application** → redirect URI `http://localhost:5678/rest/oauth2-credential/callback`.
4. `.\start-n8n.ps1` → http://localhost:5678 → create owner → Credentials → *YouTube OAuth2 API* → paste client ID/secret → Sign in with Google → choose your **channel**.
5. Import `workflows/faceless_shorts_pipeline.json`, open *YouTube: upload Short*, select your credential, save. Same for `workflows/weekly_analytics.json` (set your channel ID in *List channel videos*).

## 5. Go live
Toggle the workflow **Active**. Default cadence: 2–5 posts/day at random slots. Edit `SLOTS` in the *Prepare job* node to change.
Manual trigger any time:
```bash
curl -X POST http://localhost:5678/webhook/shortform -H "Content-Type: application/json" -H "X-Shorts-Secret: <SHORTS_WEBHOOK_SECRET from .env>" -d '{"format":"lesson"}'
```

## 6. Optional engines
- **Instagram / TikTok** — see README *Platform setup*. Fill `IG_*` / `TIKTOK_*` in `.env`; the workflow picks them up automatically.
- **Long-form radio** (watch-hours route): `python pipeline\make_lofi.py --minutes 60 --style lofi`, or wait for the weekly slot.
- **Discord report**: set `DISCORD_WEBHOOK_URL`.
- **Anthropic quality**: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` for the best scripts (paid).

## Troubleshooting
- *Execute Command node missing* → `NODES_EXCLUDE=[]` (already in `start-n8n.ps1`).
- *access to env vars denied* → `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.
- *Access to the file is not allowed* → `N8N_RESTRICT_FILE_ACCESS_TO` must include `pipeline/output`.
- *Groq 413 / TPM* → the free tier is 8k tokens/min; the pipeline already falls back to OpenRouter. Add `LLM2_API_KEY`.
- *YouTube 403 quota* → 10,000 units/day = 6 uploads. Request more in Google Cloud → Quotas.
- *Captions missing* → fonts: set `CAPTION_FONT` to one installed on your machine.

Support: open an issue on the GitHub repo.
