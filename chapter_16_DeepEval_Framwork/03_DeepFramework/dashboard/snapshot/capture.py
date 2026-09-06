"""Run every catalog metric once and save the results as a JSON snapshot.

Feeds the static showcase build. Runs serially on purpose: the judge is rate
limited, and a burst just trades a clean run for a wall of 429s.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "http://localhost:8203"
OUT = Path(__file__).parent / "results.json"
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 1

catalog = requests.get(f"{BASE}/api/catalog", timeout=15).json()
status = requests.get(f"{BASE}/api/status", timeout=15).json()

results = {}
for i, card in enumerate(catalog["cards"], 1):
    key = card["key"]
    print(f"[{i:2d}/{len(catalog['cards'])}] {card['title']:28s} ", end="", flush=True)
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{BASE}/api/run", json={"key": key, "sample": SAMPLE}, timeout=900)
        data = r.json()
        results[key] = data
        score = data.get("score")
        print(f"{data.get('status','?'):6s} "
              f"{'-' if score is None else format(score, '.3f')}  "
              f"{int((time.perf_counter()-t0)*1000)}ms")
    except Exception as e:  # noqa: BLE001
        results[key] = {"key": key, "status": "error", "score": None,
                        "reason": f"{type(e).__name__}: {e}", "rows": [],
                        "latency_ms": 0, "cases_run": 0,
                        "cases_total": card["cases_total"], "tokens": None}
        print(f"ERROR  {e}")

tokens = requests.get(f"{BASE}/api/tokens", timeout=15).json()
OUT.write_text(json.dumps({
    "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "sample": SAMPLE,
    "cards": catalog["cards"],
    "categories": catalog["categories"],
    "status": status,
    "results": results,
    "tokens": tokens,
}, indent=2))
print(f"\nwrote {OUT}  ({len(results)} cards, {tokens['total']:,} tokens)")
