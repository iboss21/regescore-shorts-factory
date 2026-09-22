"""
analytics.py — turn YouTube stats into writing guidance.

Input: --json-b64 <base64 JSON list of {id,title,publishedAt,views,likes,comments,duration}>  (from the n8n weekly workflow)
Output:
  series/analytics.json         raw snapshot + per-video velocity (views per day since publish)
  series/bible.md               "## What the data says" section rewritten with the top/bottom hooks and format stats
  stdout                        one JSON summary line
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERIES = HERE / "series"


def load_history() -> dict:
    st = json.loads((SERIES / "state.json").read_text(encoding="utf-8"))
    by_title = {}
    for h in st.get("history", []):
        for key in (h.get("title", ""), h.get("youtube_title", "")):
            if key:
                by_title[re.sub(r"\s*#shorts\s*$", "", key.strip().lower())] = h
    return by_title


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-b64", required=True)
    a = ap.parse_args()
    videos = json.loads(base64.b64decode(a.json_b64).decode("utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    hist = load_history()

    rows = []
    for v in videos:
        try:
            pub = dt.datetime.fromisoformat(v["publishedAt"].replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            pub = now
        age_days = max((now - pub).total_seconds() / 86400, 0.25)
        views = int(v.get("views") or 0)
        is_short = (v.get("duration") or 0) <= 180 and "radio" not in (v.get("title") or "").lower()
        # match to series memory by youtube title -> episode format
        fmt = "unknown"
        vt = re.sub(r"\s*#shorts\s*$", "", (v.get("title") or "").lower().strip())
        for t, h in hist.items():
            if t and (t == vt or t in vt or vt in t):
                fmt = h.get("format", "unknown")
        rows.append({
            "id": v["id"], "title": v.get("title"), "format": fmt, "short": is_short,
            "views": views, "likes": int(v.get("likes") or 0), "comments": int(v.get("comments") or 0),
            "age_days": round(age_days, 2), "views_per_day": round(views / age_days, 2),
            "like_rate": round((int(v.get("likes") or 0) / views), 4) if views else 0.0,
        })

    shorts = [r for r in rows if r["short"]]
    longs = [r for r in rows if not r["short"]]
    by_fmt = {}
    for r in shorts:
        by_fmt.setdefault(r["format"], []).append(r["views_per_day"])
    fmt_stats = {k: {"n": len(v), "median_views_per_day": round(statistics.median(v), 1)} for k, v in by_fmt.items()}
    top = sorted(shorts, key=lambda r: -r["views_per_day"])[:5]
    bottom = sorted(shorts, key=lambda r: r["views_per_day"])[:3] if len(shorts) >= 6 else []

    snapshot = {"generated": now.isoformat(), "videos": rows, "format_stats": fmt_stats,
                "total_views": sum(r["views"] for r in rows), "shorts": len(shorts), "long_form": len(longs)}
    (SERIES / "analytics.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    # rewrite the data section of the bible
    lines = ["## What the data says (auto-updated weekly; the writer must lean into this)", ""]
    lines.append(f"- Snapshot {now.date().isoformat()}: {len(shorts)} shorts, {len(longs)} long videos, {snapshot['total_views']} total views.")
    if fmt_stats:
        best = max(fmt_stats.items(), key=lambda kv: kv[1]["median_views_per_day"])
        lines.append("- Median views/day by format: " + ", ".join(f"{k} {v['median_views_per_day']}" for k, v in fmt_stats.items()) + f". Best format right now: **{best[0]}**.")
    if top:
        lines.append("- Top-performing titles (write more hooks like these):")
        for r in top:
            lines.append(f"  - \"{r['title']}\" - {r['views_per_day']} views/day, like rate {r['like_rate']:.1%}")
    if bottom:
        lines.append("- Weakest titles (avoid this angle):")
        for r in bottom:
            lines.append(f"  - \"{r['title']}\" - {r['views_per_day']} views/day")
    if not shorts:
        lines.append("- Not enough data yet. Keep the cadence; revisit next week.")
    section = "\n".join(lines) + "\n"

    bible_path = SERIES / "bible.md"
    bible = bible_path.read_text(encoding="utf-8")
    if "## What the data says" in bible:
        bible = re.sub(r"## What the data says.*?(?=\n## |\Z)", section, bible, flags=re.S)
    else:
        bible = bible.rstrip() + "\n\n" + section
    bible_path.write_text(bible, encoding="utf-8")

    print(json.dumps({"ok": True, "shorts": len(shorts), "long_form": len(longs), "total_views": snapshot["total_views"],
                      "best_format": max(fmt_stats.items(), key=lambda kv: kv[1]["median_views_per_day"])[0] if fmt_stats else None,
                      "top": [r["title"] for r in top]}))


if __name__ == "__main__":
    main()
