# GDC Daily Digest v2 — Multi-Feed Expansion Spec

## Overview

Expand the daily digest from a single GDC Vault feed to a multi-feed game industry digest covering three content types:

1. **Feed 1: GDC Vault 新 talk** (existing, unchanged)
2. **Feed 2: 新游戏发布 + 发布会** (new)
3. **Feed 3: 经典 GDC talk 回顾** (new)

Daily quota: 5-8 total embeds. Feed 1+2 combined: 3-5 (gaming news as primary). Feed 3: 1-2 (classic review).

## Feed 2: New Game Releases & Events

### Data Sources

| Source | Format | Content |
|--------|--------|---------|
| Steam new releases RSS | XML (`store.steampowered.com/feeds/newreleases.xml`) | Daily new game releases with name, description, header image, store link |
| IGN RSS | RSS | Gaming news, reviews, event coverage |
| GameSpot RSS | RSS | Gaming news, trailers, event coverage |
| 游民星空 RSS | RSS | Chinese gaming news, event roundups |

All sources are public, no API key required.

### Pipeline

```
Steam RSS ──┐
IGN RSS ────┤
GameSpot RSS┤
游民星空 RSS┘
       │
       ▼
  Deduplication (by title similarity)
       │
       ▼
  AI Filter (DeepSeek V4 Flash)
  Prompt: "Which of these are noteworthy game releases or event announcements?
           Criteria: AAA sequels, known studios, high buzz, innovative gameplay,
           Chinese gaming community interest. Return filtered JSON list."
       │
       ▼
  AI Enrichment (DeepSeek V4 Flash)
  For each selected item: generate Chinese one-liner, platforms, release date, tags
       │
       ▼
  2-4 selected items → Discord embeds
```

### Event Tracking

Sony State of Play, Nintendo Direct, Xbox Showcase, Summer Game Fest, etc. — detected via AI from media RSS when they happen. Highlighted with a dedicated "📺 发布会" embed type.

### Discord Embed Format

```
┌──────────────────────────────────────────┐
│ 🎮 新游戏发布 · Steam       colored bar │
│                                          │
│ Game Title (clickable → store page)      │
│                                          │
│ 💡 AI-generated Chinese one-liner        │
│                                          │
│ 🏷️ genre tags                            │
│ 📅 release date                          │
│ 🖥️ platforms                             │
│                                          │
│ ▶ Video (YouTube embed, auto-play)       │
│                                          │
│ 🔗 Steam / IGN / GameSpot links          │
└──────────────────────────────────────────┘
```

Video: Discord embed supports video URLs. YouTube trailer links auto-expand to an inline player.

## Feed 3: Classic GDC Talk Review

### Seed Library

Manually curated 50 classic GDC talks (2015-2025), stored as JSON. Selection criteria:
- Methodology / design philosophy (not time-bound)
- Industry-recognized classics
- Practical value for indie devs / students
- Covers Programming, Design, Art, Production

One randomly selected per day, no repeats. 50 days = one full cycle.

### AI Auto-Discovery

Monthly cron job: scrape GDC Vault for past years (2015-2025, ~2000 free talks), batch-filter via AI:
- "Looking back 5+ years, does this talk's core thesis still hold?"
- "Does it have practical reference value for today's game developers?"

New discoveries added to seed library. Keeps the pool fresh.

### Discord Embed Format (classic style — gold sidebar)

```
┌──────────────────────────────────────────┐
│ 📚 经典回顾 · GDC {year}    gold bar     │
│                                          │
│ 【{category_cn}】                         │
│ Talk Title (clickable → GDC Vault)       │
│                                          │
│ 💡 **核心观点：{bold key insight}**       │
│                                          │
│ Chinese summary with **bold keywords**    │
│ on important concepts, methodology names, │
│ and actionable takeaways.                │
│                                          │
│ 🔑 核心要点                        🏷️ 标签 │
│ • key point 1                    tag 1   │
│ • key point 2                    tag 2   │
│ • key point 3                    tag 3   │
│                                          │
│ ⭐ 适用人群: {target audience}            │
│ 📅 首次发布: {original date}             │
│ 🔗 观看原视频 (GDC Vault)                │
└──────────────────────────────────────────┘
```

### Visual Hierarchy (Classic vs New)

| Layer | Feed 1 (New GDC) | Feed 2 (Games) | Feed 3 (Classic) |
|-------|-----------------|----------------|------------------|
| Sidebar | Category color | Green `#2ECC71` | Gold `#F39C12` |
| Icon | 🎮 | 🎮/📺 | 📚 |
| Hook | 💡 one-liner | 💡 one-liner | 💡 **bold key insight** |
| Body | Plain summary | Plain summary | Summary with **bold keywords** |
| Extra | Level | Video embed | 适用人群 + 首发日期 |

## AI Prompt Changes

### Feed 2 — Filter prompt

```
You are a game industry editor. Given a list of recent game releases and news items,
select the ones that are noteworthy for a Chinese game developer audience.

Criteria:
- Sequels to well-known franchises
- Games from established studios with strong track records
- Games with innovative or unique mechanics
- Games generating significant buzz or anticipation
- Major publisher announcements (Sony, Nintendo, Microsoft, etc.)
- Games likely to interest Chinese players

Output ONLY a JSON array of selected item indices.
```

### Feed 2 — Enrichment prompt

```
For this game release/news item, output a JSON object:
{
  "one_liner_cn": "Chinese one-liner capturing what makes this game exciting (20 chars)",
  "genre_tags": ["Action RPG", "Open World"],
  "platforms": ["PC", "PS5"],
  "release_date": "2026-06-15",
  "notability": "Why this matters to game developers or players"
}
```

### Feed 3 — Classic summary prompt

```
You are a game development educator. This is a classic GDC talk from {year}.
Write a review-style summary that helps today's developers understand why this
talk still matters.

Output JSON:
{
  "core_insight": "The single most important idea from this talk, in Chinese, bold-worthy",
  "summary_cn": "2-3 sentence Chinese summary. Use **bold** markdown around key concepts, methodology names, and important terminology",
  "key_points": ["English key point 1", "key point 2", "key point 3"],
  "tags": ["tag1", "tag2", "tag3"],
  "target_audience": "关卡策划 · 独立开发者",
  "category": "Design",
  "year": 2018
}
```

## File Structure Changes

```
gdc-daily/
├── gdc_daily.py           # Updated orchestrator (3 feeds)
├── scraper.py              # Existing (GDC Vault)
├── summarizer.py           # Updated (3 prompt variants)
├── notifier.py             # Updated (classic embed style + video)
├── feeds/
│   ├── gdc_vault.py        # Feed 1: existing logic extracted
│   ├── game_releases.py    # Feed 2: Steam RSS + media RSS + AI filter
│   └── classic_gdc.py      # Feed 3: seed library + rotation + monthly discovery
├── data/
│   └── classic_seeds.json  # 50 curated classic GDC talks
├── .env
├── requirements.txt        # + feedparser for RSS
└── cache.db
```

New dependency: `feedparser` (RSS parsing, pure Python, well-maintained).

## Daily Digest Assembly

```
gdc_daily.py main()
  ├─ Feed 1: fetch_year_sessions → diff → summarize → embeds  (1-2 items)
  ├─ Feed 2: fetch_rss_all → dedup → AI filter → AI enrich → embeds  (2-4 items)
  ├─ Feed 3: pick_daily_classic → AI classic summary → classic embed  (1-2 items)
  └─ Merge all embeds → send to Discord
```

Total: 5-8 embeds in one Discord message (within 10-embed limit).

## Monthly Classic Discovery (Cron)

```
0 8 1 * * /usr/bin/python3 /home/xanwh1te/projects/gdc-daily/feeds/classic_gdc.py --discover
```

Runs on the 1st of each month. Scrapes GDC Vault 2015-2025, AI filters for timeless talks,
appends new discoveries to `classic_seeds.json`.

## Rate Limiting & Error Handling

- Feed 2: fetch RSS in parallel, 10s timeout each
- AI filter: batch all Feed 2 items in one API call
- AI enrich: one API call per selected item (max ~4/day)
- Feed 3: one API call per day for classic summary
- If any feed fails, skip it gracefully — don't block other feeds
- If all feeds produce 0 items, exit silently