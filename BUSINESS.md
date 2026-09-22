# RegesCore — business plan (living document)

Owner: iBoss. Operator: Claude (automation). Budget: **$0/month** until revenue exists.

## Thesis
Faceless short-form content is a volume game with near-zero marginal cost once automated. We win on
(1) a serialized story people come back for, (2) publishing daily on three platforms from one render,
(3) monetizing *before* platform thresholds via affiliates and by selling the factory itself.

## Revenue lines, in the order they can pay

| # | Line | Threshold | Expected timing | Status |
|---|---|---|---|---|
| 1 | Affiliate links in every description (hosting, AI tools, broker, books) | none | first sale possible in weeks | wired; needs affiliate URLs pasted into `pipeline/affiliates.json` |
| 2 | Sell the factory (Gumroad: "AI Shorts Factory", $49 launch / $99 later) | none | first sale possible in weeks; repo is the live demo | listing copy below; needs Gumroad account |
| 3 | YouTube Partner Program on RegesCore | 1k subs + 10M Shorts views/90d | 3–9 months at 1/day | daily autopilot running |
| 4 | Lofi/ambient music channel (ACE-Step local music + ComfyUI visuals, 1–3 h videos) | 1k subs + 4k watch hours | 3–6 months — long videos accrue hours fast | model downloading; generator next |
| 5 | TikTok Creator Rewards | 10k followers + 100k views/30d | after TikTok app audit | node built; account + audit pending |
| 6 | RegesCore product funnel (`G:\RegesCore-Ai`, local-first AI memory vault) | none | when the product is sellable | story already names the product |

Honest expectation: months, not days. Lines 1–2 are the only near-term cash; 3–5 compound.

## Weekly operating loop (Claude)
1. Mon: pull YouTube analytics (views, avg % viewed, CTR per episode) → update `series/bible.md` "what works" section.
2. Daily: autopilot posts 1 short (EPISODE/LESSON/LOG rotation). Review `script.json` for number sanity when notified.
3. Wed: publish 1 long lofi video (once generator exists).
4. Fri: check affiliate dashboards; adjust `affiliates.json` tags toward what converts.
5. Monthly: re-evaluate niche/format from data; kill what doesn't move.

## Costs
$0 software. Electricity for the GPU. Optional later: VPS for 24/7 n8n (~$5/mo, Hostinger).

## Gumroad listing (paste-ready)

**Title:** AI Shorts Factory — $0/month faceless YouTube/TikTok/Instagram automation (n8n + free AI)

**Subtitle:** The exact pipeline behind @RegesCore-Ai: story memory → free LLM → free voice → local AI visuals → FFmpeg → auto-post. No paid APIs.

**Description:**
Every day this system writes the next episode of a serialized story, voices it, generates cinematic scene images on a home GPU, renders a captioned 9:16 video with A/B hooks, and posts it to YouTube Shorts, Instagram Reels and TikTok — for $0 in API costs.

You get:
- The complete Python pipeline (script → voice → images → render → upload), MIT licensed
- The n8n workflow (daily schedule, Discord command trigger, YouTube/IG/TikTok posting, Discord reports)
- n8n community nodes for Instagram Reels and TikTok direct post
- A show-bible template with persistent story memory — swap in your own character and niche in 10 minutes
- Free-provider setup: Groq / OpenRouter / Gemini free tiers, edge-tts voices, ComfyUI or Pollinations images
- Setup guide for Windows/Mac/Linux, Docker compose for VPS

Requirements: a PC (GPU optional — hosted free image API works without one), free accounts on the platforms.

Live demo: youtube.com/@RegesCore-Ai · Source: github.com/iboss21/regescore-shorts-factory

**Price:** $49 launch (first 50 buyers) → $99. "Pay what you want, minimum $29" is a valid alternative for a fast start.

**FAQ**
- *Isn't it on GitHub for free?* Yes — buyers pay for the packaged setup guide, the ready-to-import n8n workflow with credentials mapped, the show-bible templates for 5 niches, and updates. The repo is the demo.
- *Will it get my channel banned?* It publishes original AI content with your own accounts through official APIs. Follow each platform's AI-content disclosure rules.
- *Do I need coding skills?* No. Copy `.env.example`, paste keys, import the workflow.

## Affiliate programs to join (you sign up; paste URLs into `pipeline/affiliates.json`)
- Hostinger Affiliate — hostinger.com/affiliates (VPS fits "the server RegesCore rents")
- ElevenLabs Affiliate — elevenlabs.io/affiliates (voice; 22% recurring)
- n8n Affiliate — n8n.io/affiliate (cloud plans)
- A brokerage program compliant in your country (keep copy non-advisory: "where RegesCore parks idle cash")
- Amazon Associates — for "the book RegesCore read this week"
