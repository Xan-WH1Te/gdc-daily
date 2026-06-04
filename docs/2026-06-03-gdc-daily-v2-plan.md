# GDC Daily Digest v2 — Multi-Feed Expansion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand daily digest from single GDC feed to 3 feeds: new GDC talks, new game releases with trailers, curated classic GDC talks.

**Architecture:** Three feed modules (existing GDC vault, new game_releases, classic_gdc) run independently, produce embeds, then merged and sent as one Discord message. AI summarizer extended with 3 prompt variants. Notifier extended with classic embed style (gold bar, bold keywords, video support).

**Tech Stack:** Python 3.12, `requests`, `feedparser` (new), `sqlite3` (stdlib), DeepSeek V4 Flash API

**Spec:** `docs/2026-06-03-gdc-daily-v2-design.md`

---

## File Structure

```
gdc-daily/
├── gdc_daily.py           # Updated: multi-feed orchestrator
├── scraper.py             # Existing: GDC Vault (unchanged)
├── summarizer.py          # Updated: 3 prompt variants
├── notifier.py            # Updated: classic embed style
├── feeds/
│   ├── __init__.py
│   ├── game_releases.py   # NEW: Feed 2 — Steam + media RSS + AI filter
│   └── classic_gdc.py     # NEW: Feed 3 — seed library + daily rotation
├── data/
│   └── classic_seeds.json # NEW: 50 curated classic GDC talks
├── requirements.txt       # Updated: +feedparser
├── .env
└── cache.db
```

---

### Task 1: Project scaffold — directories, deps, __init__

**Files:**
- Create: `projects/gdc-daily/feeds/__init__.py`
- Create: `projects/gdc-daily/data/.gitkeep`
- Modify: `projects/gdc-daily/requirements.txt`

- [ ] **Step 1: Create directories and __init__**

```bash
mkdir -p /home/xanwh1te/projects/gdc-daily/feeds
mkdir -p /home/xanwh1te/projects/gdc-daily/data
touch /home/xanwh1te/projects/gdc-daily/feeds/__init__.py
```

- [ ] **Step 2: Update requirements.txt**

```txt
requests>=2.31.0
feedparser>=6.0.0
```

- [ ] **Step 3: Verify deps**

Run: `cd /home/xanwh1te/projects/gdc-daily && python3 -c "import feedparser; print('OK', feedparser.__version__)"`
Expected: `OK 6.0.12`

- [ ] **Step 4: Commit**

```bash
git add feeds/__init__.py data/.gitkeep requirements.txt
git commit -m "chore: add feeds package scaffold and feedparser dep"
```

---

### Task 2: Feed 2 — game_releases scraper

**Files:**
- Create: `projects/gdc-daily/feeds/game_releases.py`

**Context:** Feed 2 scrapes Steam store "Popular New" page for recently released games, plus gaming media RSS feeds. Items are deduplicated then filtered/enriched by AI. Returns 2-4 curated game release items per day.

- [ ] **Step 1: Write feeds/game_releases.py**

```python
"""Feed 2: New game releases — Steam store + gaming media RSS + AI curation."""
import hashlib
import re
import time
from urllib.parse import urljoin

import feedparser
import requests

STEAM_SEARCH = "https://store.steampowered.com/search/?filter=popularnew&sort_by=Released_DESC&os=win"
STEAM_APP = "https://store.steampowered.com/app/{appid}/"

RSS_FEEDS = [
    ("IGN", "https://feeds.feedburner.com/ign/all"),
    ("GameSpot", "https://www.gamespot.com/feeds/news/"),
    ("游民星空", "https://www.gamersky.com/rss/news.xml"),
]

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = "GDC-Daily/2.0"
    return _session


def fetch_steam_new_releases():
    """Scrape Steam Popular New page for recent game titles + app IDs."""
    resp = _get_session().get(STEAM_SEARCH, timeout=30)
    resp.raise_for_status()

    items = []
    # Extract app ID + title pairs from search result rows
    for m in re.finditer(
        r'data-ds-appid="(\d+)".*?<span class="title">([^<]+)</span>',
        resp.text, re.DOTALL
    ):
        items.append({
            "source": "Steam",
            "appid": m.group(1),
            "title": m.group(2).strip(),
            "url": f"https://store.steampowered.com/app/{m.group(1)}/",
        })
    return items


def fetch_media_news():
    """Fetch recent gaming news from RSS feeds."""
    items = []
    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:  # latest 10 per source
                # Determine if game release related (basic keyword filter)
                text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
                if any(kw in text for kw in [
                    "release", "launch", "announce", "trailer",
                    "发售", "发布", "上线", "预告",
                ]):
                    items.append({
                        "source": source,
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:300],
                        "published": entry.get("published", ""),
                    })
        except Exception as e:
            print(f"  RSS {source}: {e}")
    return items


def fetch_game_detail(appid):
    """Fetch Steam store page for a game to get description, image, video."""
    url = STEAM_APP.format(appid=appid)
    resp = _get_session().get(url, timeout=30)
    if resp.status_code != 200:
        return None
    text = resp.text

    # og:image
    img = ""
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', text)
    if m:
        img = m.group(1)

    # og:description
    desc = ""
    m = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', text)
    if m:
        desc = m.group(1)

    # Release date
    date = ""
    m = re.search(r'<div class="date">([^<]+)</div>', text)
    if m:
        date = m.group(1).strip()

    # Trailer video (YouTube URL in the page)
    video = ""
    m = re.search(r'(https://www\.youtube\.com/watch\?v=[\w-]+)', text)
    if not m:
        m = re.search(r'(https://www\.youtube\.com/embed/[\w-]+)', text)
    if m:
        video = m.group(1)

    # Platforms / tags
    tags = []
    for m in re.finditer(r'<a[^>]*class="app_tag"[^>]*>([^<]+)</a>', text):
        tag = m.group(1).strip()
        if tag and tag not in ("Popular user-defined tags for this product:",):
            tags.append(tag)
    tags = tags[:5]

    return {
        "description": desc,
        "image": img,
        "release_date": date,
        "video_url": video,
        "tags": tags,
    }


def ai_filter_and_enrich(items, summarize_fn):
    """Use AI to filter for noteworthy items and enrich with metadata."""
    if not items:
        return []

    # Build a compact list for the AI
    item_list = []
    for i, item in enumerate(items):
        item_list.append(f"[{i}] [{item.get('source', '')}] {item['title']}")
    catalog = "\n".join(item_list[:30])  # Max 30 items in one batch

    filter_prompt = f"""You are a game industry editor for Chinese developers.
From this list of recent game releases and news, pick 2-4 items that are MOST noteworthy.

Criteria: AAA sequels, known studios, innovative gameplay, high buzz,
major publisher events (Sony/Nintendo/Microsoft), Chinese community interest.

Items:
{catalog}

Output ONLY a JSON array of selected indices, e.g. [0, 3, 5]"""

    result = summarize_fn(filter_prompt, "filter")
    if not result or not isinstance(result, list):
        return []

    selected = []
    for idx in result:
        if isinstance(idx, int) and idx < len(items):
            item = items[idx]
            # Enrich Steam items with store page details
            if item.get("appid"):
                detail = fetch_game_detail(item["appid"])
                if detail:
                    time.sleep(0.5)
                    item["detail"] = detail
            selected.append(item)

    return selected[:4]
```

- [ ] **Step 2: Smoke test Steam scraper**

Run:
```bash
cd /home/xanwh1te/projects/gdc-daily && python3 -c "
from feeds.game_releases import fetch_steam_new_releases, fetch_media_news
steam = fetch_steam_new_releases()
print(f'Steam: {len(steam)} games, first 3:')
for g in steam[:3]: print(f'  {g[\"title\"]} (app {g[\"appid\"]})')
news = fetch_media_news()
print(f'Media news: {len(news)} items')
"
```
Expected: 10-50 Steam games, some media news items.

- [ ] **Step 3: Commit**

```bash
git add feeds/game_releases.py
git commit -m "feat: add Feed 2 game releases scraper (Steam + media RSS)"
```

---

### Task 3: Feed 3 — classic GDC seed library + rotation

**Files:**
- Create: `projects/gdc-daily/feeds/classic_gdc.py`

- [ ] **Step 1: Write feeds/classic_gdc.py**

```python
"""Feed 3: Classic GDC talk review — seed library + daily rotation."""
import json
import os
import random
import sqlite3

SEEDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "classic_seeds.json",
)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "classic_state.db",
)


def load_seeds():
    """Load classic talk seeds from JSON file."""
    if not os.path.exists(SEEDS_PATH):
        return []
    with open(SEEDS_PATH) as f:
        return json.load(f)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shown_classics (
            talk_id TEXT PRIMARY KEY,
            shown_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def pick_daily(seeds):
    """Pick 1-2 unseen classic talks for today. Rotates through all seeds."""
    if not seeds:
        return []

    conn = init_db()
    shown = set()
    for row in conn.execute("SELECT talk_id FROM shown_classics"):
        shown.add(row[0])

    # Find unseen seeds
    unseen = [s for s in seeds if s.get("id") not in shown]

    # If all shown, reset (new cycle)
    if not unseen:
        conn.execute("DELETE FROM shown_classics")
        conn.commit()
        unseen = seeds[:]

    # Pick 1-2 randomly
    count = min(random.randint(1, 2), len(unseen))
    picked = random.sample(unseen, count)

    for s in picked:
        conn.execute(
            "INSERT OR IGNORE INTO shown_classics (talk_id) VALUES (?)",
            (s["id"],),
        )
    conn.commit()
    conn.close()
    return picked


def add_seed(talk):
    """Append a new talk to the seed library."""
    seeds = load_seeds()
    for s in seeds:
        if s["id"] == talk["id"]:
            return  # Already exists
    seeds.append(talk)
    with open(SEEDS_PATH, "w") as f:
        json.dump(seeds, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 2: Verify module loads**

Run: `cd /home/xanwh1te/projects/gdc-daily && python3 -c "from feeds.classic_gdc import load_seeds, pick_daily; print('OK')"`
Expected: `OK` (empty seeds list returns [])

- [ ] **Step 3: Commit**

```bash
git add feeds/classic_gdc.py
git commit -m "feat: add Feed 3 classic GDC seed library and rotation"
```

---

### Task 4: Classic seeds — curate 50 GDC talks

**Files:**
- Create: `projects/gdc-daily/data/classic_seeds.json`

**Context:** The seed JSON contains 50 curated classic GDC talks. Each entry has: id (GDC Vault session ID), title, url, year, category, why_classic (reason for curation). These will be populated using the existing GDC Vault scraper to discover talks from 2015-2025, then AI-curate the top 50.

- [ ] **Step 1: Discover candidate talks from past years**

Run:
```bash
cd /home/xanwh1te/projects/gdc-daily && python3 -c "
from scraper import fetch_year_sessions
import json

all_talks = []
for year in range(2015, 2026):
    try:
        sessions = fetch_year_sessions(year)
        print(f'{year}: {len(sessions)} talks')
        all_talks.extend(sessions)
    except Exception as e:
        print(f'{year}: FAILED ({e})')

print(f'Total: {len(all_talks)} talks')
# Save candidates for AI curation
with open('/tmp/gdc_candidates.json', 'w') as f:
    json.dump(all_talks, f, ensure_ascii=False, indent=2)
print('Saved to /tmp/gdc_candidates.json')
"
```
Expected: ~2000+ talks from 2015-2025 saved to candidates file.

- [ ] **Step 2: AI-curate the top 50**

Run:
```bash
cd /home/xanwh1te/projects/gdc-daily && python3 << 'PYEOF'
import json, os, requests, random

with open('/tmp/gdc_candidates.json') as f:
    all_talks = json.load(f)

# Sample ~200 for AI review (too many for one prompt)
sample = random.sample(all_talks, min(200, len(all_talks)))

# Build catalog
catalog = []
for i, t in enumerate(sample):
    catalog.append(f"[{i}] {t['year']} - {t['title_from_slug']} {t['url']}")
catalog_str = "\n".join(catalog)

prompt = f"""You are a game development educator. From this list of GDC talks (2015-2025),
select the 50 most valuable talks that are STILL worth watching today.

Criteria:
- Methodology / design philosophy (not time-bound, not engine-specific)
- Industry-recognized classics and influential talks
- Practical value for indie developers and students
- Covers Programming, Design, Art, Production across all tracks

Output ONLY a JSON array of selected indices, e.g. [3, 7, 12, ...]
Pick exactly 50 indices. Prioritize diversity of topics and years.

Talks:
{catalog_str}"""

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
resp = requests.post(
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
    json={
        "model": "deepseek-v4-flash", "max_tokens": 1000, "temperature": 0.7,
        "messages": [
            {"role": "system", "content": "You are a GDC curator. Output valid JSON arrays only."},
            {"role": "user", "content": prompt}
        ],
    },
    timeout=120,
)
resp.raise_for_status()
indices = json.loads(resp.json()["choices"][0]["message"]["content"])

seeds = []
for idx in indices:
    if isinstance(idx, int) and idx < len(sample):
        t = sample[idx]
        seeds.append({
            "id": t["session_id"],
            "title": t["title_from_slug"],
            "url": t["url"],
            "year": t["year"],
            "category": "Other",
            "why_classic": "AI-curated classic GDC talk"
        })

with open("data/classic_seeds.json", "w") as f:
    json.dump(seeds, f, ensure_ascii=False, indent=2)
print(f"Saved {len(seeds)} seeds to data/classic_seeds.json")
PYEOF
```

- [ ] **Step 3: Verify seeds file**

Run: `cd /home/xanwh1te/projects/gdc-daily && python3 -c "import json; seeds=json.load(open('data/classic_seeds.json')); print(f'{len(seeds)} seeds loaded')"`
Expected: `50 seeds loaded`

- [ ] **Step 4: Commit**

```bash
git add data/classic_seeds.json
git commit -m "feat: add 50 AI-curated classic GDC talk seeds"
```

---

### Task 5: Update summarizer — 3 prompt variants

**Files:**
- Modify: `projects/gdc-daily/summarizer.py`

**Context:** The summarizer currently has one prompt for GDC talks (Feed 1). Add two new functions: `summarize_game()` for Feed 2 items, and `summarize_classic()` for Feed 3 classic talks. Also add a raw `call_ai()` helper for the filter step.

- [ ] **Step 1: Add call_ai() helper and new summarize functions**

Replace the current `summarize()` function signature area with:

```python
def _call_ai(system_prompt, user_prompt):
    """Raw AI call returning parsed JSON. Returns None on failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("summarizer: ANTHROPIC_API_KEY not set")
        return None

    try:
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={
                "model": MODEL, "max_tokens": 800, "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"summarizer: API call failed: {e}")
        return None

    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def summarize_gdc(description, title):
    """Feed 1: Summarize a new GDC Vault talk. Existing logic preserved."""
    if not description or not description.strip():
        return _fallback(title)
    result = _call_ai(
        "You are a game development technical editor. Always output valid JSON.",
        GDC_PROMPT.format(description=description),
    )
    return result if result else _fallback(title)


def summarize_game_filter(catalog_text):
    """Feed 2 filter: Given a list of game titles, return indices of noteworthy ones."""
    result = _call_ai(
        "You are a game industry editor. Output valid JSON arrays only.",
        GAME_FILTER_PROMPT.format(catalog=catalog_text),
    )
    return result if isinstance(result, list) else []


def summarize_game_enrich(title, description):
    """Feed 2 enrich: Generate Chinese one-liner + metadata for a game."""
    if not description:
        return {"one_liner_cn": title, "genre_tags": [], "platforms": [], "release_date": "", "notability": ""}
    result = _call_ai(
        "You are a game industry editor. Always output valid JSON.",
        GAME_ENRICH_PROMPT.format(title=title, description=description[:500]),
    )
    return result if result else {"one_liner_cn": title, "genre_tags": [], "platforms": [], "release_date": "", "notability": ""}


def summarize_classic(description, title, year):
    """Feed 3: Classic GDC talk review-style summary with bold keywords."""
    if not description or not description.strip():
        return {**_fallback(title), "core_insight": title, "target_audience": "游戏开发者"}
    result = _call_ai(
        "You are a game development educator. Always output valid JSON. Use **bold** markdown around key concepts.",
        CLASSIC_PROMPT.format(description=description, title=title, year=year),
    )
    if result:
        result.setdefault("core_insight", title)
        result.setdefault("target_audience", "游戏开发者")
        return result
    return {**_fallback(title), "core_insight": title, "target_audience": "游戏开发者"}


def summarize(description, title):
    """Backward-compatible wrapper for Feed 1."""
    return summarize_gdc(description, title)
```

- [ ] **Step 2: Add new prompt constants**

Add these prompt constants after the existing `GDC_PROMPT`:

```python
GDC_PROMPT = """You are a game development technical editor..."""  # existing

GAME_FILTER_PROMPT = """You are a game industry editor for Chinese developers.
From this list of recent game releases and news, pick 2-4 items that are MOST noteworthy.

Criteria: AAA sequels, known studios, innovative gameplay, high buzz,
major publisher events (Sony/Nintendo/Microsoft), Chinese community interest.

Items:
{catalog}

Output ONLY a JSON array of selected indices, e.g. [0, 3, 5]"""

GAME_ENRICH_PROMPT = """For this game, output a JSON object:
{{
  "one_liner_cn": "Chinese one-liner capturing what makes this game exciting (within 20 chars)",
  "genre_tags": ["genre1", "genre2"],
  "platforms": ["PC", "PS5"],
  "release_date": "YYYY-MM-DD or empty string if unknown",
  "notability": "Brief reason why this matters (Chinese, 1 sentence)"
}}

Game: {title}
Description: {description}"""

CLASSIC_PROMPT = """You are a game development educator. This is a classic GDC talk from {year}.
Write a review-style summary for today's developers.

Talk: {title}
Description: {description}

Output ONLY a JSON object:
{{
  "core_insight": "The single most important idea from this talk, in Chinese (bold-worthy, within 30 chars)",
  "summary_cn": "2-3 sentence Chinese summary. Use **bold** markdown around key concepts, methodology names, and important terminology",
  "key_points": ["English key takeaway 1", "English key takeaway 2", "English key takeaway 3"],
  "tags": ["tag1", "tag2", "tag3"],
  "target_audience": "Who should watch this (Chinese, e.g. 关卡策划 · 独立开发者)",
  "category": "Programming | Design | Art | Production | Business | Other"
}}"""
```

- [ ] **Step 3: Update __init__.py to expose new functions**

```python
from summarizer import summarize, summarize_gdc, summarize_game_filter, summarize_game_enrich, summarize_classic
```

Wait, summarized is imported in gdc_daily.py. The existing `summarize()` wrapper preserves backward compatibility. New functions are imported directly where needed.

- [ ] **Step 4: Smoke test**

```bash
cd /home/xanwh1te/projects/gdc-daily && python3 -c "
from summarizer import summarize_gdc, summarize_game_filter, summarize_classic
print('summarize_gdc:', summarize_gdc('A talk about shaders', 'Shader Talk'))
print('summarize_game_filter:', summarize_game_filter('[0] Elden Ring 2\n[1] Unknown indie game'))
print('summarize_classic:', summarize_classic('A classic talk about level design', 'Level Design 101', '2018'))
"
```

- [ ] **Step 5: Commit**

```bash
git add summarizer.py
git commit -m "feat: add multi-prompt summarizer with Feed 2/3 variants"
```

---

### Task 6: Update notifier — classic embed + video

**Files:**
- Modify: `projects/gdc-daily/notifier.py`

- [ ] **Step 1: Add build_game_embed() and build_classic_embed()**

Append to notifier.py:

```python
def build_game_embed(item, detail, enrich):
    """Feed 2: Game release embed with green sidebar + video."""
    desc_parts = []
    if enrich.get("one_liner_cn"):
        desc_parts.append(f'> 💡 {enrich["one_liner_cn"]}\n')

    meta_parts = []
    if enrich.get("genre_tags"):
        meta_parts.append("  ".join(f"`{t}`" for t in enrich["genre_tags"]))
    if enrich.get("platforms"):
        meta_parts.append("🖥️ " + " · ".join(enrich["platforms"]))
    if enrich.get("release_date"):
        meta_parts.append(f'📅 {enrich["release_date"]}')
    if enrich.get("notability"):
        meta_parts.append(f'📝 {enrich["notability"]}')
    desc_parts.append("\n".join(meta_parts))

    embed = {
        "author": {"name": f'🎮 新游戏发布 · {item.get("source", "Steam")}'},
        "title": item["title"],
        "url": item["url"],
        "description": "\n".join(desc_parts),
        "color": 0x2ECC71,  # Green for game releases
        "footer": {"text": "GDC Daily Digest · 新游戏发布"},
    }

    if detail and detail.get("image"):
        embed["thumbnail"] = {"url": detail["image"]}

    if detail and detail.get("video_url"):
        embed["description"] += f'\n\n▶ [Watch Trailer]({detail["video_url"]})'

    return embed


def build_classic_embed(session, detail, summary):
    """Feed 3: Classic GDC talk embed with gold sidebar + bold keywords."""
    category = summary.get("category", "Other")
    desc_parts = []
    if summary.get("core_insight"):
        desc_parts.append(f'> 💡 **{summary["core_insight"]}**\n')
    if summary.get("summary_cn"):
        desc_parts.append(f'{summary["summary_cn"]}\n')

    embed = {
        "author": {
            "name": f'📚 经典回顾 · GDC {session.get("year", summary.get("year", ""))}'
        },
        "title": f'【{CATEGORY_CN.get(category, "综合")}】{detail.get("title") or session["title_from_slug"]}',
        "url": session["url"],
        "description": "\n".join(desc_parts),
        "color": 0xF39C12,  # Gold for classics
        "fields": [],
        "footer": {
            "text": f'⭐ {summary.get("target_audience", "游戏开发者")}  ·  GDC {session.get("year", "")}'
        },
    }

    if summary.get("key_points"):
        embed["fields"].append({
            "name": "🔑 核心要点",
            "value": "\n".join(f"• {p}" for p in summary["key_points"]),
            "inline": True,
        })

    if summary.get("tags"):
        embed["fields"].append({
            "name": "🏷️ 标签",
            "value": "  ".join(f"`{t}`" for t in summary["tags"]),
            "inline": True,
        })

    if detail.get("image"):
        embed["thumbnail"] = {"url": detail["image"]}

    return embed
```

- [ ] **Step 2: Verify embed structures**

```bash
cd /home/xanwh1te/projects/gdc-daily && python3 -c "
from notifier import build_game_embed, build_classic_embed
import json

# Test game embed
item = {'source': 'Steam', 'title': 'Elden Ring 2', 'url': 'https://store.steampowered.com/app/123/'}
detail = {'image': 'https://example.com/img.jpg', 'video_url': 'https://www.youtube.com/watch?v=abc'}
enrich = {'one_liner_cn': '魂系开放世界续作', 'genre_tags': ['Action RPG'], 'platforms': ['PC', 'PS5'], 'release_date': '2026-06-15', 'notability': 'FromSoftware年度大作'}
e1 = build_game_embed(item, detail, enrich)
print('Game embed color:', e1['color'])
print('OK')

# Test classic embed
session = {'session_id': '123', 'url': 'https://gdcvault.com/play/123/', 'year': '2018', 'title_from_slug': 'Level Design 101'}
detail = {'title': 'Level Design 101', 'description': 'A classic', 'image': ''}
summary = {'core_insight': '玩家靠好奇心而非引导线探索', 'summary_cn': '本文探讨了**三角形法则**在开放世界中的应用。', 'key_points': ['Triangle rule', 'Curiosity gap'], 'tags': ['level design'], 'target_audience': '关卡策划 · 独立开发者', 'category': 'Design', 'year': '2018'}
e2 = build_classic_embed(session, detail, summary)
print('Classic embed color:', e2['color'])
print('OK')
"
```
Expected: Game embed color `0x2ECC71`, Classic embed color `0xF39C12`.

- [ ] **Step 3: Commit**

```bash
git add notifier.py
git commit -m "feat: add game release and classic GDC embed builders"
```

---

### Task 7: Update orchestrator — multi-feed assembly

**Files:**
- Modify: `projects/gdc-daily/gdc_daily.py`

**Context:** The orchestrator now runs 3 feeds sequentially and merges their embeds. Feed 1 (existing) produces 1-2 items, Feed 2 produces 2-4, Feed 3 produces 1-2. Total 5-8 embeds sent as one Discord message.

- [ ] **Step 1: Refactor Feed 1 into a function, add Feed 2 and Feed 3 calls**

```python
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

        for session in new:
            print(f"  [{session['title_from_slug'][:50]}]")
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
        fetch_steam_new_releases, fetch_media_news, ai_filter_and_enrich
    )
    from summarizer import summarize_game_filter, summarize_game_enrich

    print("[Feed 2] Fetching game releases...")
    # 1. Fetch from Steam + media
    steam_items = fetch_steam_new_releases()
    media_items = fetch_media_news()
    all_items = steam_items[:15] + media_items
    print(f"  {len(all_items)} candidates")

    if not all_items:
        return []

    # 2. Build catalog for AI filter
    catalog = []
    for i, item in enumerate(all_items):
        catalog.append(f"[{i}] [{item.get('source', '')}] {item['title']}")
    catalog_text = "\n".join(catalog)

    # 3. AI filter
    indices = summarize_game_filter(catalog_text)
    print(f"  AI selected: {indices}")

    # 4. Build embeds for selected items
    embeds = []
    for idx in indices:
        if not isinstance(idx, int) or idx >= len(all_items):
            continue
        item = all_items[idx]
        detail = {}
        if item.get("appid"):
            from feeds.game_releases import fetch_game_detail
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
    from summarizer import summarize_classic

    print("[Feed 3] Classic GDC...")
    seeds = load_seeds()
    if not seeds:
        print("  No seeds available")
        return []

    picked = pick_daily(seeds)
    print(f"  Picked {len(picked)} classic(s)")

    embeds = []
    for talk in picked:
        session = {
            "session_id": talk["id"],
            "url": talk["url"],
            "title_from_slug": talk["title"],
            "year": talk.get("year", ""),
        }

        try:
            detail = fetch_session_detail(talk["url"])
        except Exception as e:
            print(f"  Detail failed: {e}")
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
        print("First run complete.")
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
```

- [ ] **Step 2: Update imports**

Add at top of gdc_daily.py:
```python
from summarizer import summarize_gdc, summarize_game_filter, summarize_game_enrich, summarize_classic
from notifier import build_embed, build_game_embed, build_classic_embed, send_to_discord
```

Note: `summarize` import removed (replaced by `summarize_gdc`). The `build_embed` is still used for Feed 1.

- [ ] **Step 3: Verify orchestrator loads**

Run: `cd /home/xanwh1te/projects/gdc-daily && python3 -c "import gdc_daily; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add gdc_daily.py
git commit -m "feat: add multi-feed orchestrator with Feed 1/2/3 assembly"
```

---

### Task 8: Monthly classic discovery cron

**Files:**
- Create: `projects/gdc-daily/feeds/discover_classics.py`
- Modify: crontab

- [ ] **Step 1: Create monthly discovery script**

```python
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

    # Pick 20 random candidates to review
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

    print(f"Added {new_seeds} new seeds (total reviewed: {len(candidates)})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update cron**

```bash
(crontab -l 2>/dev/null; echo '17 8 1 * * /usr/bin/python3 /home/xanwh1te/projects/gdc-daily/feeds/discover_classics.py >> /home/xanwh1te/projects/gdc-daily/logs/discover.log 2>&1') | crontab -
```

- [ ] **Step 3: Commit**

```bash
git add feeds/discover_classics.py
git commit -m "feat: add monthly classic GDC discovery script"
```

---

### Task 9: End-to-end validation

- [ ] **Step 1: Test Feed 1 (existing)**

```bash
cd /home/xanwh1te/projects/gdc-daily && python3 -c "
from gdc_daily import init_db, get_new_sessions, run_feed1_gdc_new
from scraper import fetch_year_sessions
conn = init_db()
embeds = run_feed1_gdc_new(conn)
print(f'Feed 1 OK: {len(embeds)} new GDC embeds')
conn.close()
"
```

- [ ] **Step 2: Test Feed 2 (game releases)**

```bash
cd /home/xanwh1te/projects/gdc-daily && python3 -c "
from gdc_daily import run_feed2_game_releases
embeds = run_feed2_game_releases()
print(f'Feed 2 OK: {len(embeds)} game embeds')
"
```

- [ ] **Step 3: Test Feed 3 (classic GDC) — needs seeds first**

Only run if classic_seeds.json exists from Task 4.

```bash
cd /home/xanwh1te/projects/gdc-daily && python3 -c "
from gdc_daily import run_feed3_classic_gdc
embeds = run_feed3_classic_gdc()
print(f'Feed 3 OK: {len(embeds)} classic embeds')
"
```

- [ ] **Step 4: Full integration test**

```bash
cd /home/xanwh1te/projects/gdc-daily && python3 gdc_daily.py
```
Expected: All 3 feeds run, total 5-8 embeds sent to Discord.

- [ ] **Step 5: Check Discord**

Verify the Discord channel shows embeds with all 3 styles: blue/green/gold sidebars with appropriate content.