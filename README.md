# AI Market Radar

A concept prototype for a competitive intelligence function: how you sense what is happening in AI-native travel booking, decide what matters, and get it in front of the people who can act on it.

**This is an independent concept demo. It is not a commercial product, it is not affiliated with or endorsed by any company, and the personas and curated data in it are illustrative.**

## What is here

| File | What it is |
|---|---|
| `radar-demo.html` | The working prototype. Five role views, permission walls, a sign-and-publish flow, the Assistant Lab matrix, a scored watchlist with a promotion queue, and a roadmap board. |
| `radar-prd.html` | The product requirements, clickable: architecture, data model, agent pipeline, permission matrix, phased delivery tree. |
| `radar-explainer.html` | The same system in plain language. No jargon, about an eight minute read. |
| `radar-flow.html` | One diagram of the whole system, with a walkthrough. Exports to SVG. |
| `radar_collector.py` | The published-stream collector. Pulls public news feeds, tags each item to a category, flags promotion triggers, writes `radar-data.js`. |

Everything runs as static files with no build step and no server. Nothing you do in the prototype leaves your browser.

## The idea

Three sensing streams feed five categories. Everything is scored on a fixed rubric, tiered by how much attention it earns, and either published fast and unsigned or slowly and signed by an analyst. It lands with four different teams in four different shapes, and two feedback loops send what those teams learn back into what the system watches next.

Open `radar-flow.html` for the whole thing in one picture.

## Refreshing the live feed

```
python3 radar_collector.py
```

Writes `radar-data.js`. Optional Claude triage if `ANTHROPIC_API_KEY` is set and the `anthropic` package is installed; otherwise it falls back to keyword tagging. The prototype works with or without the file.
