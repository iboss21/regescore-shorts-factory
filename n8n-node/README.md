# n8n-nodes-social-shorts

[![Build](https://img.shields.io/github/actions/workflow/status/iboss21/n8n-nodes-social-shorts/ci.yml?label=build)](https://github.com/iboss21/n8n-nodes-social-shorts/actions)
[![License: MIT](https://img.shields.io/github/license/iboss21/n8n-nodes-social-shorts)](LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178c6?logo=typescript\&logoColor=white)](#)
![n8n Community Node](https://img.shields.io/badge/n8n-community%20node-blue)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Stars](https://img.shields.io/github/stars/iboss21/n8n-nodes-social-shorts?style=social)](https://github.com/iboss21/n8n-nodes-social-shorts/stargazers)

<!-- These npm badges will light up after publish -->

[![npm](https://img.shields.io/npm/v/n8n-nodes-social-shorts?color=cb3837\&logo=npm)](https://www.npmjs.com/package/n8n-nodes-social-shorts)
[![npm downloads](https://img.shields.io/npm/dm/n8n-nodes-social-shorts.svg)](https://www.npmjs.com/package/n8n-nodes-social-shorts)

**Publish short vertical videos from n8n** to:

* **Instagram Reels** (Graph API — *implemented*)
* **YouTube Shorts** (*stub included; PRs welcome*)
* **TikTok** Content Posting (*stub included; PRs welcome*)

Works great with presigned S3 URLs and the included Discord-triggered, “make-it-viral” workflow (story → voiceover → subtitles → render → cross-post → Notion report → Discord follow-up).

---

## Table of contents

* [Features](#features)
* [Architecture](#architecture)
* [Install](#install)
* [Usage in n8n](#usage-in-n8n)
* [Credentials & Permissions](#credentials--permissions)
* [Example workflows](#example-workflows)
* [FAQ](#faq)
* [Roadmap](#roadmap)
* [Contributing](#contributing)
* [Security & Privacy](#security--privacy)
* [License](#license)

---

## Features

* **Instagram Reels Publisher**: create container → publish, with caption and optional “Share to Feed”.
* **S3-friendly**: optimized for **presigned S3 MP4 URLs** (safe, fast, no public buckets).
* **Developer-first**: small, typed, no heavy dependencies.
* **Examples included**: Discord slash-command to n8n → LLM plan → TTS → FFmpeg (A/B hooks) → S3 → IG/YT/TikTok → Notion + Discord report.
* **Contribution-ready**: YouTube + TikTok nodes scaffolded to invite clean PRs (OAuth, resumable upload, content publish).

---

## Architecture

```
Discord Slash Command
      │
      ▼
n8n Webhook  ──► LLM (Story + Hooks + Hashtags)
      │                 │
      │                 ├─► TTS (voice.mp3)
      │                 └─► SRT (subtitles)
      ▼
FFmpeg Render (A/B variants, 9:16) ──► S3 Upload + Presign
      │                                   │
      ├────────► Instagram Reels (Graph API: container → publish)
      ├────────► YouTube Shorts (resumable upload)   [stub]
      └────────► TikTok Content Posting              [stub]
      │
      ├────────► Notion log (what/how/links)
      └────────► Discord follow-up (report)
```

---

## Install

### Option A — Local dev (recommended for now)

```bash
# Clone or download the repo
npm i
npm run build

# Install into n8n custom nodes
mkdir -p ~/.n8n/custom/n8n-nodes-social-shorts
cp -r dist ~/.n8n/custom/n8n-nodes-social-shorts

# Restart n8n
```

**Docker**

```yaml
# In your n8n docker-compose, mount the built dist:
volumes:
  - ./dist:/home/node/.n8n/custom/n8n-nodes-social-shorts
```

### Option B — npm (after publish)

```bash
npm install n8n-nodes-social-shorts
# copy node files from node_modules/n8n-nodes-social-shorts/dist to ~/.n8n/custom/n8n-nodes-social-shorts
```

---

## Usage in n8n

**Instagram Reels Publisher** node fields:

* **IG Business User ID** — numeric ID (not @handle)
* **Video URL** — publicly reachable MP4 (best: S3 presigned)
* **Caption** — trimmed to platform limits
* **Share to Feed** — boolean
* **Access Token** — Graph API token with `instagram_content_publish`
* *(Optional)* Graph API version (default `v19.0`)

**Typical pattern**

1. Upload MP4 to S3 → Presign URL.
2. Pass URL + caption to **Instagram Reels Publisher**.
3. Node returns `creationId` and publish JSON.

---

## Credentials & Permissions

* **Instagram / Facebook**:

  * IG Business or Creator account linked to a Facebook Page.
  * App in **Live** mode with **`instagram_content_publish`**.
  * Long-lived **User Access Token**.
* **YouTube** *(stub)*:

  * OAuth scope **`youtube.upload`**, resumable upload (init → `PUT`).
* **TikTok** *(stub)*:

  * Approved app + content posting scopes (init upload → upload → publish).

---

## Example workflows

> See the `examples/` folder (or the **workflows/** bundle in releases).

* `discord_to_viral_short_AB_multi.json`
  A/B hooks, caption sanitizer, TTS, SRT, FFmpeg render, S3 presign, IG/YT/TikTok posting, Notion log, Discord report.
* `discord_to_viral_short.json`
  Single variant.
* `shortform_machine_multi.json`
  “Autoposter” loop with per-platform toggles.

**Discord Worker (Cloudflare)**

* Minimal Worker in `discord-to-n8n-worker/`:

  * Verifies signatures, sends deferred ACK, forwards payload to your n8n webhook.
  * Configure `DISCORD_PUBLIC_KEY` and `N8N_WEBHOOK_URL` in `wrangler.toml`, then `npx wrangler deploy`.

---

## FAQ

**Why S3 presigned URLs instead of direct binary uploads?**
They’re reliable, fast, and don’t expose your bucket. Instagram Reels supports `video_url` for containers.

**Will YouTube/TikTok be implemented?**
Yes—stubs are intentionally small to invite PRs. See the [Roadmap](#roadmap).

**What about covers/thumbnails and A/B testing?**
The example workflow renders **two variants** (different hooks) from the same TTS/SRT, doubling creative coverage with minimal cost. Cover frame extraction is on the roadmap.

**Can I swap TTS or LLM vendors?**
Yes. The workflow is modular: drop in Azure/Google/Coqui TTS or any LLM; keep the same render/post pipeline.

---

## Roadmap

* [ ] **YouTube Shorts**: OAuth + resumable upload (init, upload, finalize)
* [ ] **TikTok Content Posting**: init, upload, publish + policy handling
* [ ] Binary upload fallback (no external URL)
* [ ] Cover frame (timestamp) + thumbnail upload where supported
* [ ] Policy guardrails per platform (bad-word rewrites, length clamping)
* [ ] Scheduled A/B scoring (fetch views after 24–72h; mark winner in Notion)

---

## Contributing

Contributions are welcome—see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

**Quick dev loop**

```bash
npm i
npm run build
mkdir -p ~/.n8n/custom/n8n-nodes-social-shorts
cp -r dist ~/.n8n/custom/n8n-nodes-social-shorts
# restart n8n, test the node
```

**Please:**

* Keep error messages descriptive (include Graph/TikTok/YT JSON).
* Avoid heavy dependencies.
* Update README/examples when behavior changes.

---

## Security & Privacy

* Store platform tokens in **n8n Credentials** or environment variables—never commit secrets.
* Prefer presigned URLs that expire quickly (≤1h).
* Respect platform content policies and rate limits.

---

## License

MIT © [iBoss](https://github.com/iboss21)

---