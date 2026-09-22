"""
monetize.py — the money layer appended to every description/caption.

Reads pipeline/affiliates.json:
{
  "disclosure": "Some links are affiliate links...",
  "links": [
    {"id": "hostinger", "label": "The server RegesCore rents (Hostinger VPS)", "url": "https://...", "tags": ["server","hosting","vps","box"]},
    ...
  ],
  "always": ["hostinger"],        # ids always included
  "max_links": 3
}

pick_links(text, hashtags) -> ordered list of link dicts relevant to this episode (matched on tags), plus the 'always' ones.
footer_youtube(...) / footer_caption(...) render platform-specific blocks. Links with a placeholder URL are skipped,
so nothing broken ever ships.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
AFF_PATH = Path(os.getenv("AFFILIATES_FILE", HERE / "affiliates.json"))


def _load() -> Dict:
    if not AFF_PATH.exists():
        return {"links": [], "always": [], "max_links": 3, "disclosure": ""}
    return json.loads(AFF_PATH.read_text(encoding="utf-8"))


def _live(link: Dict) -> bool:
    u = (link.get("url") or "").strip()
    return u.startswith("http") and "PASTE" not in u and "example.com" not in u


def pick_links(text: str, hashtags: List[str]) -> List[Dict]:
    cfg = _load()
    hay = (text + " " + " ".join(hashtags)).lower()
    scored = []
    for link in cfg.get("links", []):
        if not _live(link):
            continue
        score = sum(1 for t in link.get("tags", []) if re.search(rf"\b{re.escape(t.lower())}\b", hay))
        if link.get("id") in cfg.get("always", []):
            score += 100
        if score > 0:
            scored.append((score, link))
    scored.sort(key=lambda x: -x[0])
    return [l for _, l in scored[: int(cfg.get("max_links", 3))]]


def footer_youtube(text: str, hashtags: List[str], channel_links: Dict[str, str] | None = None) -> str:
    cfg = _load()
    links = pick_links(text, hashtags)
    lines: List[str] = []
    if links:
        lines.append("")
        lines.append("Tools from this episode:")
        for l in links:
            lines.append(f"• {l['label']}: {l['url']}")
    if channel_links:
        lines.append("")
        for name, url in channel_links.items():
            if url and "PASTE" not in url:
                lines.append(f"{name}: {url}")
    if links and cfg.get("disclosure"):
        lines.append("")
        lines.append(cfg["disclosure"])
    return "\n".join(lines)


def footer_caption(text: str, hashtags: List[str], link_in_bio: str = "") -> str:
    """Instagram/TikTok don't render URLs in captions; point to the bio link instead."""
    links = pick_links(text, hashtags)
    if not links:
        return ""
    return "\n\nTools I used are in the bio link." if not link_in_bio else f"\n\nTools I used: {link_in_bio}"
