# Operations — how to run the RegesCore machine day to day

## Is it running?
- n8n: http://localhost:5678 → *Executions* tab shows every run (green = posted). Log file: `n8n.log`.
- Health check: `curl http://localhost:5678/healthz` → `{"status":"ok"}`.
- ComfyUI must be running (`G:\ComfyUI`, port 8188) for local images/music; otherwise images fall back to Pollinations and music is skipped.
- Start after reboot: `.\start-n8n.ps1` (leave it open) and start ComfyUI.

## What posts when
- **Shorts**: cron slots 08:00, 11:00, 14:00, 17:00, 20:00; each day a stable random 2–5 of them fire. Format by slot: 08 episode · 11 lesson · 14 log · 17 episode · 20 lesson.
- **Radio (long-form)**: Wednesday and Sunday 12:00, styles rotate lofi → ambient → synth → piano.
- **Analytics**: Monday 07:00 → `pipeline/series/analytics.json` and the *What the data says* section of the bible.

## Post something now
```bash
# next story beat (episode | lesson | log)
curl -X POST http://localhost:5678/webhook/shortform -H "Content-Type: application/json" -H "X-Shorts-Secret: $SECRET" -d '{"format":"episode"}'
# a one-hour radio video
curl -X POST http://localhost:5678/webhook/shortform -H "Content-Type: application/json" -H "X-Shorts-Secret: $SECRET" -d '{"kind":"radio","style":"ambient","minutes":60}'
# re-post an already rendered job
curl -X POST http://localhost:5678/webhook/shortform -H "Content-Type: application/json" -H "X-Shorts-Secret: $SECRET" -d '{"from_result":"G:/.../pipeline/output/<job>/result.json"}'
```
`$SECRET` = `SHORTS_WEBHOOK_SECRET` in `pipeline/.env`.

## Pause / resume
- n8n → workflow *RegesCore AI - Shorts Pipeline* → toggle **Active** off. Nothing posts. Toggle on to resume.
- Only stop YouTube but keep rendering: set `"platforms":{"yt":false}` in a webhook call, or edit the defaults in the *Prepare job* node.

## Review a video before it is public
Render without posting, look, then post:
```bash
python pipeline/make_short.py --series --format episode --variants 2      # renders + uploads to S3, no YouTube
# check pipeline/output/<job>/script.json and short_A.mp4, then:
curl ... -d '{"from_result":"<job>/result.json"}'
```
Or unlist a bad one afterwards: YouTube Studio → Content → visibility.

## Steer the show
- `pipeline/series/bible.md` — tone, formats, ethics, number rules, and the auto-written data section. The writer reads it every time.
- `pipeline/series/state.json` — the memory. Edit `open_threads` to plant plot points; never edit `episode` by hand unless you know why.
- `pipeline/.env` — voice (`EDGE_VOICE`), image style (`IMAGE_STYLE`), caption size, music volume, cadence-independent knobs.

## Money
- `pipeline/affiliates.json` — paste affiliate URLs; the footer starts including them on the next render.
- `BUSINESS.md` — plan, Gumroad listing copy. `dist/ai-shorts-factory-vX.zip` — `git archive` of the repo for buyers.

## Known limits
- YouTube API quota: 6 uploads/day max (10,000 units). Cadence is capped at 5.
- Groq free: 8,000 tokens/min → the writer sometimes falls back to OpenRouter (50 free requests/day). Both are fine at 5 posts/day.
- ComfyUI shares one GPU: a radio render (~40 min) and a short at the same time will just take longer.
- TikTok posts stay private until TikTok audits the developer app.

## Where things are
| Thing | Path |
|---|---|
| renders | `pipeline/output/<timestamp-title>/` (`short_A.mp4`, `short_B.mp4`, `scenes/`, `bed.mp3`, `script.json`, `result.json`) |
| radio | `pipeline/output/<timestamp>-radio-<style>-<min>min/` (`radio.mp4`, `thumbnail.jpg`, `tracks/`) |
| n8n DB | `%USERPROFILE%\.n8n\database.sqlite` |
| custom nodes | `%USERPROFILE%\.n8n\custom\n8n-nodes-social-shorts` |
| ComfyUI models | `G:\ComfyUI\models\checkpoints` (Juggernaut-XL, ACE-Step) |
