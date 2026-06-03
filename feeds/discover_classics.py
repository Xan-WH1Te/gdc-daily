#!/usr/bin/env python3
"""Monthly classic GDC discovery — scan past years for new timeless talks."""
import json, os, random, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import fetch_year_sessions, fetch_session_detail
from summarizer import _call_ai
from feeds.classic_gdc import add_seed

DISCOVERY_PROMPT = """You are a GDC curator. Given this talk's description,
is it STILL worth watching today (5+ years later)?

Criteria:
- Methodology / design philosophy (not time-bound)
- Practical value for indie devs and students
- Not overly engine-specific or obsolete

Talk: {title} ({year})
Description: {description}

Output ONLY a JSON object: {{"worth_it": true/false, "why": "1 sentence reason in Chinese"}}"""


def main():
    # Load .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if k not in os.environ:
                        os.environ[k] = v

    all_talks = []
    for year in range(2015, 2026):
        try:
            sessions = fetch_year_sessions(year)
            all_talks.extend(sessions)
            print(f"{year}: {len(sessions)}")
        except Exception as e:
            print(f"{year}: FAILED ({e})")

    candidates = random.sample(all_talks, min(20, len(all_talks)))
    new_seeds = 0

    for t in candidates:
        try:
            detail = fetch_session_detail(t["url"])
        except Exception:
            continue
        if not detail or not detail.get("description"):
            continue

        result = _call_ai(
            "You are a GDC curator. Output valid JSON only.",
            DISCOVERY_PROMPT.format(
                title=detail.get("title") or t["title_from_slug"],
                year=t["year"],
                description=detail["description"][:500],
            ),
        )
        if result and result.get("worth_it"):
            add_seed({
                "id": t["session_id"],
                "title": detail.get("title") or t["title_from_slug"],
                "url": t["url"],
                "year": t["year"],
                "category": result.get("category", "Other"),
                "why_classic": result.get("why", ""),
            })
            new_seeds += 1
            print(f"  Added: {t['title_from_slug'][:60]}")

        time.sleep(1)

    print(f"Added {new_seeds} new seeds (reviewed {len(candidates)})")


if __name__ == "__main__":
    main()
