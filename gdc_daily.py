#!/usr/bin/env python3
"""GDC Daily Digest — scrape, summarize, and push GDC Vault talks to Discord."""
import os
import sqlite3
import sys
import time

from scraper import fetch_year_sessions, fetch_session_detail
from summarizer import summarize_gdc, summarize_game_filter, summarize_game_enrich, summarize_classic
from notifier import build_embed, build_game_embed, build_classic_embed, send_to_discord

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache.db")
YEARS = [int(y.strip()) for y in os.environ.get("GDC_YEARS", "2026").split(",")]


def _load_env():
    """Load .env file if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    if key not in os.environ:
                        os.environ[key] = val


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
    print(f"Seeded {len(sessions)} sessions into cache.")


def run_feed1_gdc_new(conn):
    """Feed 1: New GDC Vault talks. Returns list of embeds."""
    embeds = []
    for year in YEARS:
        print(f"[Feed 1] Fetching GDC {year} sessions...")
        try:
            sessions = fetch_year_sessions(year)
        except Exception as e:
            print(f"  Failed: {e}")
            continue

        new = get_new_sessions(conn, sessions)
        print(f"  {len(sessions)} total, {len(new)} new")

        for i, session in enumerate(new):
            print(f"  [{i+1}/{len(new)}] {session['title_from_slug'][:50]}...")
            try:
                detail = fetch_session_detail(session["url"])
            except Exception as e:
                print(f"    Detail failed: {e}")
                continue
            if detail is None:
                continue

            title = detail.get("title") or session["title_from_slug"]
            summary = summarize_gdc(detail.get("description", ""), title)
            embed = build_embed(session, detail, summary)
            embeds.append(embed)

            conn.execute(
                "INSERT OR IGNORE INTO seen_sessions (session_id, title, url, year) VALUES (?, ?, ?, ?)",
                (session["session_id"], title, session["url"], str(year)),
            )
            conn.commit()
            time.sleep(1)

    print(f"[Feed 1] {len(embeds)} embeds")
    return embeds


def run_feed2_game_releases():
    """Feed 2: New game releases. Returns list of embeds."""
    from feeds.game_releases import (
        fetch_steam_new_releases, fetch_media_news, fetch_game_detail
    )

    print("[Feed 2] Fetching game releases...")
    steam_items = fetch_steam_new_releases()
    media_items = fetch_media_news()
    all_items = steam_items[:15] + media_items
    print(f"  {len(all_items)} candidates ({len(steam_items)} Steam, {len(media_items)} news)")

    if not all_items:
        return []

    catalog = []
    for i, item in enumerate(all_items):
        catalog.append(f"[{i}] [{item.get('source', '')}] {item['title']}")
    catalog_text = "\n".join(catalog)

    indices = summarize_game_filter(catalog_text)
    if not indices:
        print("  AI filter returned no selections")
        return []
    print(f"  AI selected: {indices}")

    embeds = []
    for idx in indices:
        if not isinstance(idx, int) or idx >= len(all_items):
            continue
        item = all_items[idx]
        print(f"  [{item['title'][:50]}]")

        detail = {}
        if item.get("appid"):
            detail = fetch_game_detail(item["appid"]) or {}
            time.sleep(0.5)

        enrich = summarize_game_enrich(
            item["title"],
            detail.get("description", item.get("summary", "")),
        )
        embed = build_game_embed(item, detail, enrich)
        embeds.append(embed)

    print(f"[Feed 2] {len(embeds)} embeds")
    return embeds


def run_feed3_classic_gdc():
    """Feed 3: Classic GDC talk review. Returns list of embeds."""
    from feeds.classic_gdc import load_seeds, pick_daily

    print("[Feed 3] Classic GDC...")
    seeds = load_seeds()
    if not seeds:
        print("  No seeds available")
        return []

    picked = pick_daily(seeds)
    if not picked:
        print("  None picked")
        return []
    print(f"  Picked {len(picked)} classic(s)")

    embeds = []
    for talk in picked:
        print(f"  [{talk['title'][:50]}]")
        session = {
            "session_id": talk["id"],
            "url": talk["url"],
            "title_from_slug": talk["title"],
            "year": talk.get("year", ""),
        }

        try:
            detail = fetch_session_detail(talk["url"])
        except Exception as e:
            print(f"    Detail failed: {e}")
            detail = None

        if detail is None:
            detail = {"title": talk["title"], "description": "", "image": ""}

        summary = summarize_classic(
            detail.get("description", ""),
            detail.get("title") or talk["title"],
            talk.get("year", "2018"),
        )
        embed = build_classic_embed(session, detail, summary)
        embeds.append(embed)
        time.sleep(1)

    print(f"[Feed 3] {len(embeds)} embeds")
    return embeds


def main():
    _load_env()
    missing_vars = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing_vars.append("ANTHROPIC_API_KEY")
    if not os.environ.get("GDC_WEBHOOK_URL"):
        missing_vars.append("GDC_WEBHOOK_URL")
    if missing_vars:
        print(f"Missing env vars: {', '.join(missing_vars)}")
        sys.exit(1)

    conn = init_db()

    # First run: seed Feed 1 cache
    if is_first_run(conn):
        for year in YEARS:
            print(f"Seeding GDC {year} cache...")
            try:
                sessions = fetch_year_sessions(year)
                seed_cache(conn, sessions)
            except Exception as e:
                print(f"Failed: {e}")
        conn.close()
        print("First run complete. Cache seeded. Run again tomorrow.")
        sys.exit(0)

    # Run all feeds
    all_embeds = []
    all_embeds.extend(run_feed1_gdc_new(conn))
    all_embeds.extend(run_feed2_game_releases())
    all_embeds.extend(run_feed3_classic_gdc())

    conn.close()

    if all_embeds:
        print(f"\nTotal: {len(all_embeds)} embeds. Sending to Discord...")
        send_to_discord(all_embeds)
        print("Done.")
    else:
        print("No new content to report.")


if __name__ == "__main__":
    main()