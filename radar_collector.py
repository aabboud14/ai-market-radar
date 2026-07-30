#!/usr/bin/env python3
"""AI Market Radar — published-stream collector (agent v1).

Pulls real headlines from public Google News RSS feeds for the Radar watchlist,
filters and tags them, and writes radar-data.js next to radar-demo.html.
The dashboard picks the file up automatically; without it, the demo falls back
to illustrative data.

Usage:
    python3 radar_collector.py

No dependencies required for the basic run (Python stdlib only).
Optional LLM triage: if the `anthropic` SDK is installed and credentials are
available (ANTHROPIC_API_KEY or `ant auth login`), each item is classified,
deduped, and summarized by Claude. Without it, keyword tagging is used.

    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 radar_collector.py
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "radar-data.js")

RECENT_DAYS = 45
MAX_PER_QUERY = 3
MAX_TOTAL = 14

# (player label, query, default category)
QUERIES = [
    ("Mindtrip", '"Mindtrip" AI travel', "plat"),
    ("Sabre", '"Sabre" travel AI agent', "rails"),
    ("OpenAI / ChatGPT", "ChatGPT travel booking agent", "plat"),
    ("Google / Gemini", "Gemini AI travel booking", "plat"),
    ("Perplexity", "Perplexity travel booking", "plat"),
    ("Microsoft / Copilot", "Copilot AI travel booking", "plat"),
    ("Travelport", '"Travelport" AI agent', "rails"),
    ("Duffel", '"Duffel" flights API', "rails"),
    ("Navan", '"Navan" travel AI agent', "rails"),
    ("Payments", "agentic commerce payments travel checkout", "pay"),
    ("Protocols", '"Model Context Protocol" travel booking', "proto"),
    ("Suppliers", "airline direct AI agent booking", "supplier"),
]

CATS = ["plat", "rails", "proto", "supplier", "pay"]

RELEVANCE = [
    "ai", "agent", "agentic", "assistant", "chatgpt", "gemini", "claude",
    "copilot", "perplexity", "mindtrip", "sabre", "travelport", "duffel",
    "navan", "booking", "travel", "gds", "ndc", "mcp", "payment",
    "checkout", "itinerary", "airline", "hotel",
]

KEYWORD_CATS = [
    ("pay", ["payment", "checkout", "paypal", "stripe", "wallet", "agentic commerce"]),
    ("proto", ["protocol", "mcp", "standard", "interoperab"]),
    ("supplier", ["airline direct", "hotel direct", "direct booking", "bypass"]),
]

# Promotion triggers (watchlist rubric, step 3): any of these forces an
# immediate tier review instead of waiting for the quarterly re-score.
TRIGGER_WORDS = [
    ("funding", ["raises", "series a", "series b", "series c", "funding round",
                 "funding", "acquires", "acquisition", "acquired", "merger",
                 "m&a", "investment round"]),
    ("partnership", ["partners with", "partnership", "collaborate", "collaboration",
                     "teams up", "integration", "integrates", "alliance",
                     "selects", "joins forces"]),
    ("launch", ["launches", "launch", "unveils", "introduces", "rolls out",
                "debuts", "goes live", "releases", "opens "]),
]


def detect_trigger(item):
    hay = (item["title"] + " " + item["desc"]).lower()
    for name, words in TRIGGER_WORDS:
        if any(w in hay for w in words):
            return name
    return None


def fetch_feed(query):
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def norm_title(title):
    return re.sub(r"[^a-z0-9]+", "", title.lower())[:80]


def parse_items(xml_bytes, player, default_cat):
    items = []
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        source = (item.findtext("source") or "").strip()
        desc = strip_html(item.findtext("description") or "")
        if not title or not link:
            continue
        # Google News appends " - Source" to titles
        if source and title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].rstrip()
        # Google News descriptions usually just repeat the headline — drop those
        if norm_title(desc).startswith(norm_title(title)[:40]):
            desc = ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            dt = None
        items.append(
            {
                "player": player,
                "cat": default_cat,
                "title": title,
                "url": link,
                "source": source or "Google News",
                "desc": desc[:220],
                "dt": dt,
            }
        )
    return items


def relevant(item):
    hay = (item["title"] + " " + item["desc"]).lower()
    return any(k in hay for k in RELEVANCE)


def keyword_cat(item):
    hay = (item["title"] + " " + item["desc"]).lower()
    for cat, words in KEYWORD_CATS:
        if any(w in hay for w in words):
            return cat
    return item["cat"]


def collect():
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    seen = set()
    collected = []
    for player, query, cat in QUERIES:
        try:
            xml_bytes = fetch_feed(query)
        except Exception as exc:  # network or HTTP failure: skip this feed
            print(f"  ! {player}: fetch failed ({exc})", file=sys.stderr)
            continue
        kept = 0
        for item in parse_items(xml_bytes, player, cat):
            if kept >= MAX_PER_QUERY:
                break
            if item["dt"] and item["dt"] < cutoff:
                continue
            if not relevant(item):
                continue
            key = norm_title(item["title"])
            if key in seen:
                continue
            seen.add(key)
            item["cat"] = keyword_cat(item)
            item["trigger"] = detect_trigger(item)
            collected.append(item)
            kept += 1
        print(f"  · {player}: {kept} item(s)")
    collected.sort(key=lambda x: x["dt"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return collected[:MAX_TOTAL]


def claude_triage(items):
    """Optional second pass: Claude classifies, filters, and summarizes items.

    Returns (updated_items, mode). Falls back silently when the SDK or
    credentials are unavailable.
    """
    try:
        import anthropic
    except ImportError:
        return items, "keywords (anthropic SDK not installed)"

    payload = [
        {"i": i, "title": it["title"], "source": it["source"], "desc": it["desc"]}
        for i, it in enumerate(items)
    ]
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "i": {"type": "integer"},
                        "keep": {"type": "boolean"},
                        "cat": {"type": "string", "enum": CATS},
                        "player": {"type": "string"},
                        "why": {"type": "string"},
                        "trigger": {"type": "string", "enum": ["funding", "partnership", "launch", "none"]},
                    },
                    "required": ["i", "keep", "cat", "player", "why", "trigger"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    system = (
        "You triage competitive-intelligence headlines for a travel-tech market "
        "radar at a GDS company. Categories: plat=AI assistant platforms, "
        "rails=travel infrastructure/GDS competitors, proto=protocols and "
        "standards (MCP, agentic commerce specs), supplier=airlines/hotels "
        "going direct to AI agents, pay=payments and agentic checkout. "
        "Drop items that are irrelevant to AI-assistant travel competition "
        "(generic travel news, stock coverage, listicles). For kept items, "
        "write one crisp 'why it matters' sentence for an analyst audience. "
        "Also tag the promotion trigger per item: funding (round or M&A), "
        "partnership (new partnership or integration go-live), launch (product "
        "launch that changes core capability); otherwise none. Triggers force "
        "an immediate watchlist tier review, so only tag real events, not "
        "commentary about them."
    )
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.environ.get("RADAR_MODEL", "claude-opus-5"),
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": json.dumps(payload)}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason == "refusal":
            return items, "keywords (triage request refused)"
        text = next(b.text for b in response.content if b.type == "text")
        verdicts = {v["i"]: v for v in json.loads(text)["items"]}
    except Exception as exc:
        return items, f"keywords (Claude triage unavailable: {type(exc).__name__})"

    out = []
    for i, item in enumerate(items):
        v = verdicts.get(i)
        if v is None or not v["keep"]:
            continue
        item["cat"] = v["cat"] if v["cat"] in CATS else item["cat"]
        item["player"] = v["player"] or item["player"]
        item["desc"] = v["why"] or item["desc"]
        t = v.get("trigger")
        item["trigger"] = None if t in (None, "none") else t
        out.append(item)
    return out, "claude"


def main():
    print("AI Market Radar collector — published stream")
    print(f"Window: last {RECENT_DAYS} days · cap {MAX_TOTAL} items\n")
    items = collect()
    if not items:
        print("\nNo items collected (network down or feeds empty). Nothing written.")
        sys.exit(1)

    items, mode = claude_triage(items)
    print(f"\nTriage mode: {mode}")

    signals = []
    for it in items:
        dt = it["dt"]
        signals.append(
            {
                "date": dt.strftime("%b %-d") if dt else "Recent",
                "iso": dt.strftime("%Y-%m-%d") if dt else "",
                "stream": "published",
                "cat": it["cat"],
                "player": it["player"],
                "title": it["title"],
                "body": it["desc"],
                "source": f"{it['source']} · via Google News RSS",
                "url": it["url"],
                "trigger": it.get("trigger"),
                "live": True,
            }
        )

    meta = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(signals),
        "triage": mode,
        "window_days": RECENT_DAYS,
    }
    with open(OUT_PATH, "w") as f:
        f.write("// Generated by radar_collector.py — do not edit by hand\n")
        f.write("window.LIVE_SIGNALS = ")
        f.write(json.dumps(signals, indent=2, ensure_ascii=False))
        f.write(";\nwindow.LIVE_META = ")
        f.write(json.dumps(meta, ensure_ascii=False))
        f.write(";\n")

    n_trig = sum(1 for s in signals if s.get("trigger"))
    print(f"Promotion triggers detected: {n_trig} (feed the watchlist promotion queue)")
    print(f"Wrote {len(signals)} live signals to {OUT_PATH}")
    print("Open radar-demo.html and the feed appears in Signals, marked LIVE.")


if __name__ == "__main__":
    main()
