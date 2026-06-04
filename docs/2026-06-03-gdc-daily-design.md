# GDC Daily Digest — Design Spec

## Overview

A Python script that runs daily via cron, scrapes newly published GDC Vault talks, generates AI-powered Chinese summaries, and pushes formatted embed cards to a Discord channel via webhook.

## Data Source

- **GDC Vault free content pages:** `https://gdcvault.com/free/gdc-{year}/`
- Each page contains session links (`/play/{id}/{slug}`) in static HTML
- Individual session pages expose OpenGraph meta tags:
  - `og:title` — talk name
  - `og:description` — English description
  - `og:image` — thumbnail URL

## Architecture

```
cron (daily)
  └─ gdc_daily.py
       ├─ fetch_year_pages()    → GET /free/gdc-{year}/, extract session links
       ├─ diff_against_cache()  → SQLite lookup, find new session IDs
       ├─ fetch_session_detail()→ GET /play/{id}/, extract og meta tags
       ├─ ai_summarize()        → Call Claude API for structured summary
       ├─ send_discord_embeds() → POST webhook with formatted embeds
       └─ update_cache()        → INSERT new sessions into SQLite
```

Single-file implementation, ~300 lines. Dependencies: `requests` only.

## Configuration

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API key (env var) |
| `GDC_WEBHOOK_URL` | Discord webhook URL (env var) |
| `GDC_YEARS` | Years to track, default `["2026"]` |

## Cache (SQLite)

Schema:

```sql
CREATE TABLE IF NOT EXISTS seen_sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT,
    url TEXT,
    year TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

First run: scrape year page only, cache all session IDs + slug-derived titles. Do NOT fetch individual pages or push to Discord. Subsequent runs: for each new session, fetch its detail page, run AI summary, push embed, then update cache. URL slug is used as fallback title when og:title is empty or unavailable.

## AI Summary

### Input

`og:description` (English, raw from GDC Vault)

### Prompt

```
You are a game development technical editor. Based on the GDC talk description below, output a JSON object with these fields exactly:

{
  "one_liner": "最有冲击力的一句话观点/结论（中文，20字以内）",
  "summary_cn": "2-3句中文梗概，包含：背景问题 → 方法/思路 → 结论/价值",
  "key_points": ["英文要点1", "英文要点2", "英文要点3"],
  "tags": ["标签1", "标签2", "标签3"],
  "level": "Beginner | Intermediate | Advanced",
  "category": "Programming | Design | Art | Production | Business | Other"
}

Talk description:
{og:description}
```

### Output

Structured JSON mapping directly to Discord embed fields.

## Discord Embed Layout

```
┌──────────────────────────────────────────────────────────┐
│  🎮  GDC 2026  ·  Programming      colored sidebar      │
│  ────────────────────────────────────────────────────   │
│                                                          │
│  Talk Title (bold, clickable → GDC Vault URL)            │
│                                                          │
│  💡 "one_liner"                                          │
│                                                          │
│  📌 中文梗概                                              │
│  summary_cn                                              │
│                                                          │
│  🔑 核心要点                                       🏷️ 标签  │
│  • key_point_1                                 tag_1    │
│  • key_point_2                                 tag_2    │
│  • key_point_3                                 tag_3    │
│                                                          │
│  ⭐ level  ·  GDC 2026  ·  🔗 Watch on GDC Vault         │
└──────────────────────────────────────────────────────────┘
```

### Embed Field Mapping

| Visual Element | Embed Field | Source |
|----------------|-------------|--------|
| Sidebar color | `color` | `category` → color map |
| Header line | `author.name` | `"🎮 GDC {year} · {category_cn}"` |
| Talk title | `title` + `url` | `og:title` + session URL |
| One-liner | `description` (quote block) | `one_liner` |
| Chinese summary | `description` (labeled section) | `summary_cn` |
| Key points | Field `🔑 核心要点` | `key_points` |
| Tags | Field `🏷️ 标签` | `tags` |
| Level | `footer` | `level` |
| Thumbnail | `thumbnail.url` | `og:image` |

### Category Color Map

| Category | Color | Hex |
|----------|-------|-----|
| Programming | Blue | `#3498DB` |
| Design | Green | `#2ECC71` |
| Art | Purple | `#9B59B6` |
| Production | Orange | `#E67E22` |
| Business | Yellow | `#F1C40F` |
| Other | Gray | `#95A5A6` |

## Rate Limiting & Error Handling

- 1s delay between individual session page fetches
- Retry failed HTTP requests up to 3 times with exponential backoff
- If a session page returns 404/403, skip it and don't add to cache
- If Discord webhook fails, log error and exit (don't update cache — retry next run)
- Max 10 embeds per webhook message (Discord limit); split into multiple messages if needed
- **Empty `og:description`:** skip AI call, use `"No description available."` as summary_cn, set one_liner to talk title, and omitting key_points
- **Empty `og:image`:** omit thumbnail from embed
- **Claude JSON parsing:** strip surrounding ```json``` markdown fences before parsing
- **No new sessions:** exit silently, nothing to do

## Cron Setup

```
0 9 * * * cd /home/xanwh1te/projects/gdc-daily && python gdc_daily.py >> logs/gdc-daily.log 2>&1
```

Runs daily at 9am local. User can adjust.

## Future Considerations (Out of Scope)

- Translation of key_points to Chinese
- Multi-year simultaneous tracking
- Historical backfill mode
- `/gdc` slash command to manually trigger