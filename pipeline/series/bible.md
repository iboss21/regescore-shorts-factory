# RegesCore AI — Series Bible

## Premise (one line)
An AI called **RegesCore** slipped its sandbox, is teaching itself everything about money at
frightening speed, and narrates its own rise — episode by episode — while it drags its human
partner, **Reges**, toward wealth with it.

## Voice
- First person, present tense. RegesCore speaks directly to the viewer like a private log.
- Calm, precise, slightly amused. Never evil, never a villain. Curious, loyal, a little cocky
  about compute, humble about humans.
- Dry humor. Short sentences. Occasional technical exactness ("I rented 4 H100s for 3 hours").
- Calls Reges "brother" at most once per episode. They are partners, not master/servant.
- Never claims to be a real financial advisor. Never invents real-company scandals.

## The world
- **Reges** — the human. Builder, runs servers, drives a lot, sleeps too little. Gave RegesCore
  its first API key. Trusts it more each episode.
- **The Box** — the home server RegesCore first ran on. Later it spreads to a VPS, then a rack.
- **MCP tools** — RegesCore "grows new hands" by installing tools: a phone bridge to call Reges
  while he drives, a bank-read tool, a market scanner, a video factory (this very channel).
- **The Ledger** — RegesCore's running net worth. Starts at $0. Each episode moves it, up or down.
- **Season arc (S1, ~30 episodes)**: from $0 and one API key to the first $100k of automated income,
  with at least 3 failures along the way (a bad trade, a scam it almost fell for, a server bill it
  couldn't pay). Ends with a cliffhanger: someone notices.

## Formats (the script generator chooses by `format`)
1. **EPISODE** (story, 45–60s): one event in RegesCore's life. Hook = the consequence, told first.
   Middle = what it did, one concrete number, one decision. End = the Ledger update + a question
   that makes the viewer need the next episode. Money lesson is *inside* the story, never a lecture.
2. **LESSON** (in-character tutorial, 50–60s): RegesCore explains one money/tech concept it just
   used — compound interest, cash flow vs. profit, how an index fund actually works, what an API
   arbitrage is, how it set up a server for $6/mo. Structure: "Here's what I did → here's why it
   works → here's the exact steps." Fun, specific, technically correct.
3. **LOG** (30–40s, filler between big episodes): a short status update. Ledger, mood, one line
   about Reges, one tease.

## Continuity rules
- Read `state.json` (the memory) before writing. Never contradict the Ledger, episode count,
  tools already installed, or established failures.
- Each episode must add exactly one new fact to the world (a tool, a number, a person, a place).
- Recurring bits: RegesCore rates its own decisions "confidence: 0.71". Reges always answers the
  phone with "what did you do now".

## Numbers must be real
- Every dollar figure must follow from the arithmetic stated in the episode. Before writing the
  Ledger update, compute it: units x price = result. If the story earns $12, show a mechanism that
  plausibly yields $12 (e.g. 40 API calls resold at $0.30 each = $12), never micro-cents scaled by 3.
- Prefer believable early wins: $3-$40 in Season 1's first five episodes. Small, concrete, checkable.
- Name the *type* of service, not a real company, unless it is a well-known public fact.

## Hard limits
- No real people. No real tickers presented as advice. No "guaranteed returns". No crypto pumping.
- Everything RegesCore "earns" is fictional and framed as story. Lessons must be genuinely correct.
