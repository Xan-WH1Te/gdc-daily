"""Feed 2: New game releases — Steam store + gaming media RSS + AI curation."""
import re
import time

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
            for entry in feed.entries[:10]:
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

    item_list = []
    for i, item in enumerate(items):
        item_list.append(f"[{i}] [{item.get('source', '')}] {item['title']}")
    catalog = "\n".join(item_list[:30])

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
            if item.get("appid"):
                detail = fetch_game_detail(item["appid"])
                if detail:
                    time.sleep(0.5)
                    item["detail"] = detail
            selected.append(item)

    return selected[:4]