#!/usr/bin/env python3
"""GDC Daily Digest — scrape, summarize, and push GDC Vault talks to Discord."""
import os
import sqlite3
import sys
import time

from scraper import fetch_year_sessions, fetch_session_detail
from summarizer import summarize
from notifier import build_embed, send_to_discord

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache.db")
YEARS = [int(y.strip()) for y in os.environ.get("GDC_YEARS", "2026").split(",")]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            year TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def get_new_sessions(conn, year_sessions):
    """Return sessions from year_sessions that aren't in the cache yet."""
    existing = set()
    for row in conn.execute("SELECT session_id FROM seen_sessions"):
        existing.add(row[0])
    return [s for s in year_sessions if s["session_id"] not in existing]


def is_first_run(conn):
    return conn.execute("SELECT count(*) FROM seen_sessions").fetchone()[0] == 0


def seed_cache(conn, sessions):
    """Bulk-insert session IDs from year page on first run. No individual page fetch."""
    for s in sessions:
        conn.execute(
            "INSERT OR IGNORE INTO seen_sessions (session_id, title, url, year) VALUES (?, ?, ?, ?)",
            (s["session_id"], s["title_from_slug"], s["url"], str(s["year"])),
        )
    conn.commit()
    print(f"First run: seeded {len(sessions)} sessions into cache. No push.")


def main():
    missing_vars = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing_vars.append("ANTHROPIC_API_KEY")
    if not os.environ.get("GDC_WEBHOOK_URL"):
        missing_vars.append("GDC_WEBHOOK_URL")
    if missing_vars:
        print(f"Missing env vars: {', '.join(missing_vars)}")
        sys.exit(1)

    conn = init_db()
    all_embeds = []

    # First run: seed all years' sessions into cache, no push
    if is_first_run(conn):
        for year in YEARS:
            print(f"Seeding GDC {year} cache...")
            try:
                sessions = fetch_year_sessions(year)
            except Exception as e:
                print(f"Failed to fetch year {year}: {e}")
                continue
            seed_cache(conn, sessions)
        conn.close()
        print("First run complete. Cache seeded. Run again tomorrow for new talks.")
        sys.exit(0)

    for year in YEARS:
        print(f"Fetching GDC {year} sessions...")
        try:
            sessions = fetch_year_sessions(year)
        except Exception as e:
            print(f"Failed to fetch year {year}: {e}")
            continue

        new = get_new_sessions(conn, sessions)
        print(f"  {len(sessions)} total, {len(new)} new")

        if not new:
            continue

        for i, session in enumerate(new):
            print(f"  [{i+1}/{len(new)}] {session['title_from_slug'][:60]}...")

            try:
                detail = fetch_session_detail(session["url"])
            except Exception as e:
                print(f"    Failed to fetch detail: {e}")
                continue

            if detail is None:
                print(f"    Skipped (404/403)")
                continue

            title = detail.get("title") or session["title_from_slug"]
            summary = summarize(detail.get("description", ""), title)
            embed = build_embed(session, detail, summary)
            all_embeds.append(embed)

            # Cache after successful processing
            conn.execute(
                "INSERT OR IGNORE INTO seen_sessions (session_id, title, url, year) VALUES (?, ?, ?, ?)",
                (session["session_id"], title, session["url"], str(year)),
            )
            conn.commit()

            time.sleep(1)  # Rate limit between fetches

    if all_embeds:
        print(f"Sending {len(all_embeds)} embed(s) to Discord...")
        send_to_discord(all_embeds)
        print("Done.")
    else:
        print("No new sessions to report.")

    conn.close()


if __name__ == "__main__":
    main()