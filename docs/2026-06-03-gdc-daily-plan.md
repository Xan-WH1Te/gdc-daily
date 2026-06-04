# GDC Daily Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python script that scrapes GDC Vault daily, generates AI-powered Chinese summaries, and pushes formatted Discord embed cards via webhook.

**Architecture:** 4-file package — `gdc_daily.py` orchestrates, `scraper.py` handles HTTP parsing, `summarizer.py` calls Claude API, `notifier.py` builds and sends Discord embeds. SQLite cache prevents duplicate pushes.

**Tech Stack:** Python 3.12, `requests`, `sqlite3` (stdlib), Anthropic API (raw HTTP)

**Spec:** `docs/2026-06-03-gdc-daily-design.md`

---

## File Structure

```
gdc-daily/
├── gdc_daily.py           # Entry point + orchestrator (~80 lines)
├── scraper.py             # GDC Vault HTTP + HTML parsing (~60 lines)
├── summarizer.py          # Claude API call + JSON parsing (~60 lines)
├── notifier.py            # Discord embed build + webhook send (~80 lines)
├── requirements.txt       # requests
└── docs/
    └── 2026-06-03-gdc-daily-design.md
```

---

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `projects/gdc-daily/requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```txt
requests>=2.31.0
```

- [ ] **Step 2: Install dependencies**

Run: `cd /home/xanwh1te/projects/gdc-daily && pip install -r requirements.txt`

- [ ] **Step 3: Create empty package files to verify structure**

Run:
```bash
cd /home/xanwh1te/projects/gdc-daily
touch scraper.py summarizer.py notifier.py gdc_daily.py
ls -la *.py
```
Expected: 4 .py files exist.

---

### Task 2: Scraper module — fetch year page + session links

**Files:**
- Create: `projects/gdc-daily/scraper.py`

- [ ] **Step 1: Write scraper.py**

```python
"""GDC Vault HTML scraping — session list + og meta tags."""
import re
import time
from urllib.parse import urljoin

import requests

BASE_URL = "https://gdcvault.com"
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = "GDC-Daily/1.0"
    return _session


def fetch_year_sessions(year):
    """Return list of {session_id, url, title_from_slug, year} from a year page."""
    short = str(year)[-2:]
    url = f"{BASE_URL}/free/gdc-{short}/"
    resp = _get_session().get(url, timeout=30)
    resp.raise_for_status()

    sessions = []
    seen = set()
    for m in re.finditer(r'href="(/play/(\d+)/([^"]*))"', resp.text):
        path, sid, slug = m.group(1), m.group(2), m.group(3)
        if sid in seen:
            continue
        seen.add(sid)
        title = slug.replace("-", " ").strip() if slug else f"Session {sid}"
        sessions.append({
            "session_id": sid,
            "url": urljoin(BASE_URL, path),
            "title_from_slug": title,
            "year": str(year),
        })
    return sessions


def _get_meta(text, prop):
    m = re.search(rf'<meta\s+property="og:{prop}"\s+content="([^"]*)"', text)
    return m.group(1) if m else ""


def fetch_session_detail(url, retries=3):
    """Return {title, description, image} from a session page. Retries on failure."""
    s = _get_session()
    for attempt in range(retries):
        try:
            resp = s.get(url, timeout=30)
            if resp.status_code in (404, 403):
                return None
            resp.raise_for_status()
            return {
                "title": _get_meta(resp.text, "title"),
                "description": _get_meta(resp.text, "description"),
                "image": _get_meta(resp.text, "image"),
            }
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    return None
```

- [ ] **Step 2: Smoke-test the year-page scraper**

Run: `cd /home/xanwh1te/projects/gdc-daily && python3 -c "from scraper import fetch_year_sessions; s = fetch_year_sessions(2026); print(f'Found {len(s)} sessions'); print(s[0])"`
Expected: `Found 259 sessions` (or similar count) + first session dict printed.

- [ ] **Step 3: Smoke-test session detail scraper**

Run: `cd /home/xanwh1te/projects/gdc-daily && python -c "
from scraper import fetch_year_sessions, fetch_session_detail
sessions = fetch_year_sessions(2026)
detail = fetch_session_detail(sessions[0]['url'])
print(detail)
"`
Expected: dict with title, description, image fields (image may be empty).

---

### Task 3: Summarizer module — Claude API call

**Files:**
- Create: `projects/gdc-daily/summarizer.py`

- [ ] **Step 1: Write summarizer.py**

```python
"""Claude API summarization — structured JSON from GDC talk descriptions."""
import json
import os
import re

import requests

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

PROMPT = """You are a game development technical editor. Based on the GDC talk description below, output ONLY a JSON object (no markdown fences, no extra text) with these exact fields:

{
  "one_liner": "Most impactful insight/conclusion from this talk, in Chinese, within 20 characters",
  "summary_cn": "2-3 sentence Chinese summary covering: background problem → approach/method → conclusion/value",
  "key_points": ["Key takeaway 1 in English", "Key takeaway 2", "Key takeaway 3"],
  "tags": ["tag1", "tag2", "tag3"],
  "level": "Beginner | Intermediate | Advanced",
  "category": "Programming | Design | Art | Production | Business | Other"
}

Talk description:
{description}"""


def summarize(description, title):
    """Return structured summary dict from Claude API. Falls back gracefully on empty input."""
    if not description or not description.strip():
        return _fallback(title)

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 500,
            "messages": [
                {"role": "user", "content": PROMPT.format(description=description)}
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"]

    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _fallback(title)


def _fallback(title):
    return {
        "one_liner": title,
        "summary_cn": "暂无简介",
        "key_points": [],
        "tags": [],
        "level": "Intermediate",
        "category": "Other",
    }
```

- [ ] **Step 2: Smoke-test the summarizer (needs ANTHROPIC_API_KEY set)**

Run: `cd /home/xanwh1te/projects/gdc-daily && python -c "
from scraper import fetch_year_sessions, fetch_session_detail
from summarizer import summarize
sessions = fetch_year_sessions(2026)
detail = fetch_session_detail(sessions[0]['url'])
if detail and detail['description']:
    result = summarize(detail['description'], detail['title'] or sessions[0]['title_from_slug'])
    import json; print(json.dumps(result, ensure_ascii=False, indent=2))
else:
    print('No description found, skip')
"`
Expected: structured JSON with all 6 fields printed.

- [ ] **Step 3: Test fallback on empty description**

Run: `cd /home/xanwh1te/projects/gdc-daily && python -c "from summarizer import summarize; r = summarize('', 'Test Talk'); print(r)"`
Expected: fallback dict with `summary_cn: "暂无简介"`.

---

### Task 4: Notifier module — Discord embed + webhook

**Files:**
- Create: `projects/gdc-daily/notifier.py`

- [ ] **Step 1: Write notifier.py**

```python
"""Discord embed formatting and webhook delivery."""
import os

import requests

WEBHOOK_URL = os.environ.get("GDC_WEBHOOK_URL", "")

CATEGORY_COLORS = {
    "Programming": 0x3498DB,
    "Design": 0x2ECC71,
    "Art": 0x9B59B6,
    "Production": 0xE67E22,
    "Business": 0xF1C40F,
    "Other": 0x95A5A6,
}

CATEGORY_CN = {
    "Programming": "编程技术",
    "Design": "游戏设计",
    "Art": "美术视觉",
    "Production": "制作管理",
    "Business": "商业市场",
    "Other": "综合",
}


def build_embed(session, detail, summary):
    """Assemble a single Discord embed dict from scraped + summarized data."""
    category = summary.get("category", "Other")
    color = CATEGORY_COLORS.get(category, 0x95A5A6)

    # Description: one-liner quote + Chinese summary
    desc_parts = []
    if summary.get("one_liner"):
        desc_parts.append(f'> 💡 {summary["one_liner"]}\n')
    if summary.get("summary_cn"):
        desc_parts.append(f'**📌 中文梗概**\n{summary["summary_cn"]}')

    embed = {
        "author": {
            "name": f'🎮 GDC {session["year"]} · {CATEGORY_CN.get(category, "综合")}'
        },
        "title": detail["title"] or session["title_from_slug"],
        "url": session["url"],
        "description": "\n".join(desc_parts),
        "color": color,
        "fields": [],
        "footer": {
            "text": f'⭐ {summary.get("level", "N/A")}  ·  GDC {session["year"]}'
        },
    }

    # Key points field
    if summary.get("key_points"):
        embed["fields"].append({
            "name": "🔑 核心要点",
            "value": "\n".join(f"• {p}" for p in summary["key_points"]),
            "inline": True,
        })

    # Tags field
    if summary.get("tags"):
        embed["fields"].append({
            "name": "🏷️ 标签",
            "value": "  ".join(f"`{t}`" for t in summary["tags"]),
            "inline": True,
        })

    # Thumbnail
    if detail.get("image"):
        embed["thumbnail"] = {"url": detail["image"]}

    return embed


def send_to_discord(embeds):
    """Send embeds to Discord webhook. Splits into batches of 10 (Discord limit)."""
    if not WEBHOOK_URL:
        print("GDC_WEBHOOK_URL not set, skipping Discord send")
        return

    for i in range(0, len(embeds), 10):
        batch = embeds[i : i + 10]
        payload = {"embeds": batch}
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=30)
        resp.raise_for_status()
        print(f"Sent {len(batch)} embed(s) to Discord")
```

- [ ] **Step 2: Verify embed structure locally**

Run: `cd /home/xanwh1te/projects/gdc-daily && python -c "
from notifier import build_embed
import json

session = {'session_id': '123', 'url': 'https://example.com', 'title_from_slug': 'Test Talk', 'year': '2026'}
detail = {'title': 'Test Talk Full', 'description': 'A great talk about shaders', 'image': 'https://example.com/thumb.png'}
summary = {'one_liner': '着色器优化是关键', 'summary_cn': '本演讲讨论了着色器优化', 'key_points': ['Point 1', 'Point 2'], 'tags': ['shaders', 'optimization'], 'level': 'Advanced', 'category': 'Programming'}

embed = build_embed(session, detail, summary)
print(json.dumps(embed, ensure_ascii=False, indent=2))
"`
Expected: valid Discord embed JSON dict printed.

---

### Task 5: Main orchestrator — wire everything together

**Files:**
- Create: `projects/gdc-daily/gdc_daily.py`

- [ ] **Step 1: Write gdc_daily.py**

```python
#!/usr/bin/env python33
"""GDC Daily Digest — scrape, summarize, and push GDC Vault talks to Discord."""
import json
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
    first = is_first_run(conn)
    all_embeds = []

    for year in YEARS:
        print(f"Fetching GDC {year} sessions...")
        try:
            sessions = fetch_year_sessions(year)
        except Exception as e:
            print(f"Failed to fetch year {year}: {e}")
            continue

        new = get_new_sessions(conn, sessions)
        print(f"  {len(sessions)} total, {len(new)} new")

        if first:
            seed_cache(conn, sessions)
            print("First run complete. Cache seeded. Run again tomorrow for new talks.")
            sys.exit(0)

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

            title = detail["title"] or session["title_from_slug"]
            summary = summarize(detail["description"], title)
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


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script loads without errors**

Run: `cd /home/xanwh1te/projects/gdc-daily && python -c "import gdc_daily; print('Module loaded OK')"`
Expected: `Module loaded OK` (will fail on `main()` call due to missing env vars, but import should work).

---

### Task 6: First-run initialization (seed the cache)

- [ ] **Step 1: Run first time to seed cache (no push)**

Set both env vars, then run:
```bash
cd /home/xanwh1te/projects/gdc-daily
export ANTHROPIC_API_KEY="your-key"
export GDC_WEBHOOK_URL="your-webhook"
python gdc_daily.py
```

Expected on first run: `Fetching GDC 2026 sessions... 259 total, 259 new` → `First run: seeded 259 sessions into cache. No push.`

After the run completes, verify cache:
```bash
python -c "import sqlite3; conn = sqlite3.connect('cache.db'); print('Cached:', conn.execute('SELECT count(*) FROM seen_sessions').fetchone()[0])"
```
Expected: `Cached: 259`

- [ ] **Step 2: Run again to verify no duplicates**

```bash
cd /home/xanwh1te/projects/gdc-daily && python gdc_daily.py
```
Expected: `259 total, 0 new` → `No new sessions to report.`

---

### Task 7: Cron setup

- [ ] **Step 1: Create logs directory**

```bash
mkdir -p /home/xanwh1te/projects/gdc-daily/logs
```

- [ ] **Step 2: Add cron entry**

Run: `crontab -l 2>/dev/null; echo "Add this line:"; echo '7 9 * * * cd /home/xanwh1te/projects/gdc-daily && /usr/bin/python3 gdc_daily.py >> logs/gdc-daily.log 2>&1'`

The user should manually add the cron line. Using minute 7 (not 0) to avoid thundering herd.

---

### Task 8: End-to-end validation

- [ ] **Step 1: Simulate a "new session" scenario**

Temporarily remove one session from cache to simulate a new discovery:
```bash
cd /home/xanwh1te/projects/gdc-daily
python -c "
import sqlite3
conn = sqlite3.connect('cache.db')
# Remove one session so next run treats it as new
conn.execute('DELETE FROM seen_sessions WHERE rowid = (SELECT rowid FROM seen_sessions LIMIT 1)')
conn.commit()
print('Removed 1 session from cache')
"
```

- [ ] **Step 2: Run and verify single-session push**

```bash
cd /home/xanwh1te/projects/gdc-daily && python gdc_daily.py
```
Expected: `259 total, 1 new` → processes 1 session → pushes 1 embed to Discord.

- [ ] **Step 3: Verify the Discord message**

Check the Discord channel — should see one embed card with title, Chinese summary, key points, tags, color sidebar, and link.

- [ ] **Step 4: Restore cache state**

```bash
cd /home/xanwh1te/projects/gdc-daily && python -c "
import sqlite3
conn = sqlite3.connect('cache.db')
print('Current cache size:', conn.execute('SELECT count(*) FROM seen_sessions').fetchone()[0])
"
```
Cache should now have full 259 again (the "removed" session was re-added).