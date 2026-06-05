"""Telegram notification — HTML-formatted digest with dedup + threading."""
import hashlib
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import requests

API_BASE = "https://api.telegram.org/bot"
SEP = "━━━━━━━━━━━━━━━━━━"

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pushed_items.db")


def _get_credentials():
    token = os.environ.get("GDC_TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("GDC_TELEGRAM_CHAT_ID", "")
    return token, chat_id


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bold_markers(text):
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text


def _tags_to_hashtags(tags):
    if not tags:
        return ""
    seen = set()
    result = []
    for t in tags:
        tag = f"#{_esc(t).replace(' ', '_').replace('-', '_')}"
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return "  ".join(result)


# ── Dedup ──────────────────────────────────────────────

def _init_dedup_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pushed_items (
            content_hash TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            pushed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Cleanup old entries
    conn.execute("DELETE FROM pushed_items WHERE pushed_at < datetime('now', '-30 days')")
    conn.commit()
    return conn


def _hash_content(title, source):
    raw = f"{title.lower().strip()}|{source.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def is_duplicate(title, source):
    """Check if this title+source combo was already pushed."""
    conn = _init_dedup_db()
    h = _hash_content(title, source)
    row = conn.execute("SELECT 1 FROM pushed_items WHERE content_hash = ?", (h,)).fetchone()
    conn.close()
    return row is not None


def mark_pushed(title, source):
    """Record that this item has been pushed."""
    conn = _init_dedup_db()
    h = _hash_content(title, source)
    conn.execute(
        "INSERT OR IGNORE INTO pushed_items (content_hash, title, source) VALUES (?, ?, ?)",
        (h, title, source),
    )
    conn.commit()
    conn.close()


def dedup_game_items(items):
    """Merge duplicate game items from different sources. Returns deduped list."""
    seen = {}
    result = []
    for item in items:
        key = item["title"].lower().strip().rstrip(".")
        # Normalize common suffixes
        for suffix in [" trailer", " revealed", " announced", " launch", " delay"]:
            if key.endswith(suffix):
                key = key[:-len(suffix)]
        if key in seen:
            existing = seen[key]
            # Merge sources
            src = existing.get("merged_sources", [existing.get("source", "")])
            src.append(item.get("source", ""))
            existing["merged_sources"] = list(set(src))
        else:
            seen[key] = item
            result.append(item)
    return result


# ── Sending ────────────────────────────────────────────

def _send_message(html_text, reply_to=None, disable_preview=False, silent=False, retries=2):
    """Send a message to Telegram. Returns message_id on success, None on failure."""
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        return None

    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{API_BASE}{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": html_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": disable_preview,
                    "disable_notification": silent,
                    **(dict(reply_to_message_id=reply_to) if reply_to else {}),
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("ok"):
                return data["result"]["message_id"]
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                print(f"telegram: send failed: {e}")
    return None


def _should_silent():
    """Don't send notification sounds late at night (22:00-07:00 UTC)."""
    hour = datetime.now(timezone.utc).hour
    return hour >= 22 or hour < 7


# ── Digest Assembly ────────────────────────────────────

def send_digest(all_messages):
    """Send the daily digest as a header + threaded replies."""
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        print("GDC_TELEGRAM_TOKEN or GDC_TELEGRAM_CHAT_ID not set, skipping Telegram")
        return

    if not all_messages:
        return

    silent = _should_silent()
    print(f"Sending {len(all_messages)} messages to Telegram{' (silent)' if silent else ''}...")

    # Count by type
    game_count = sum(1 for m in all_messages if m["type"] == "game")
    gdc_count = sum(1 for m in all_messages if m["type"] == "gdc_talk")
    classic_count = sum(1 for m in all_messages if m["type"] == "classic")

    # 1. Send header
    now = datetime.now()
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.weekday()]
    date_str = f"{now.year}年{now.month}月{now.day}日 {weekday}"

    header_parts = [
        f"📋 <b>GDC 游戏日报</b>",
        f"📅 {date_str}",
        "",
        SEP,
    ]
    if game_count:
        header_parts.append(f"🎮 新游戏发布 <b>{game_count}</b> 条")
    if gdc_count:
        header_parts.append(f"🔵 GDC 新 Talk <b>{gdc_count}</b> 条")
    if classic_count:
        header_parts.append(f"📚 经典回顾 <b>{classic_count}</b> 条")
    header_parts.extend([
        "",
        SEP,
        f"#GDC日报  #{now.strftime('%Y%m%d')}",
    ])

    header_id = _send_message(
        "\n".join(header_parts),
        disable_preview=True,
        silent=silent,
    )

    if not header_id:
        print("telegram: header send failed, aborting")
        return

    # 2. Send each item as reply
    sent = 0
    for msg in all_messages:
        time.sleep(0.4)
        # Game messages: enable link preview for Steam thumbnails
        disable_preview = msg["type"] != "game"
        msg_id = _send_message(
            msg["text"],
            reply_to=header_id,
            disable_preview=disable_preview,
            silent=True,  # replies always silent
        )
        if msg_id:
            sent += 1

    print(f"Telegram: {sent}/{len(all_messages)} messages sent")


# ── Formatting ─────────────────────────────────────────

def format_gdc_talk(session, detail, summary):
    """Feed 1: New GDC Vault talk."""
    title = detail.get("title") or session["title_from_slug"]
    url = session["url"]
    year = session["year"]
    category = summary.get("category", "Other")
    category_cn = {"Programming": "编程技术", "Design": "游戏设计",
                   "Art": "美术视觉", "Production": "制作管理",
                   "Business": "商业市场"}.get(category, "综合")

    lines = [
        f'🎮 <b>{_esc(title)}</b>',
        f'🔵 #GDC{year}  #新Talk  #{_esc(category_cn)}',
        "",
        f'🔗 <a href="{url}">Watch on GDC Vault</a>',
    ]

    if summary.get("one_liner"):
        lines.extend(["", f'💡 <i>{_esc(summary["one_liner"])}</i>'])

    if summary.get("summary_cn"):
        lines.extend(["", f"<u>📌 中文梗概</u>", _esc(summary["summary_cn"])])

    if summary.get("key_points"):
        lines.append("")
        lines.append("<u>🔑 核心要点</u>")
        for p in summary["key_points"]:
            lines.append(f"  • {_esc(p)}")

    tags = _tags_to_hashtags(summary.get("tags", []))
    level_str = {"Beginner": "入门", "Intermediate": "进阶", "Advanced": "深入"}
    level = level_str.get(summary.get("level", ""), "")
    footer = f"⭐ {_esc(level)}" if level else ""
    lines.extend(["", SEP, f"{tags}  {footer}".strip()])

    return {"type": "gdc_talk", "text": "\n".join(lines)}


def format_game_release(item, detail, enrich):
    """Feed 2: New game release with official Chinese name."""
    title = item["title"]
    url = item["url"]
    source = item.get("source", "Steam")
    merged = item.get("merged_sources", [])
    name_cn = detail.get("name_cn", "") if detail else ""

    # Title: official CN name / EN name (no CN → EN only)
    if name_cn and name_cn != title:
        display_title = f"{_esc(name_cn)}  /  {_esc(title)}"
    else:
        display_title = _esc(title)

    source_tag = "  ".join(f"#{_esc(s)}" for s in ([source] + merged))

    lines = [
        f'🎮 <b>{display_title}</b>',
        f'🟢 {source_tag}  #新游戏发布',
        "",
        f'🔗 <a href="{url}">Store Page</a>',
    ]

    if enrich.get("one_liner_cn"):
        lines.extend(["", f'💡 <i>{_esc(enrich["one_liner_cn"])}</i>'])

    meta = []
    if enrich.get("genre_tags"):
        genre_str = "  ".join(f"<code>{_esc(t)}</code>" for t in enrich["genre_tags"])
        meta.append(genre_str)
    if enrich.get("platforms"):
        platforms = " · ".join(_esc(p) for p in enrich["platforms"])
        meta.append(f"🖥️ {platforms}")
    if enrich.get("release_date"):
        meta.append(f'📅 {_esc(enrich["release_date"])}')
    if meta:
        lines.extend(["", "\n".join(meta)])

    stats = []
    if detail and detail.get("metacritic"):
        mc = detail["metacritic"]
        stats.append(f'🎯 <b>{mc["score"]}</b> ({mc.get("reviews", 0)} reviews)')
    if detail and detail.get("price"):
        price_str = f'💰 {detail["price"]}'
        if detail.get("discount"):
            price_str += f'  <s>{detail.get("og_price", "")}</s>'
        stats.append(price_str)
    if stats:
        lines.extend(["", "  ".join(stats)])

    if enrich.get("notability"):
        lines.extend(["", f'📝 {_esc(enrich["notability"])}'])

    if detail and detail.get("video_url"):
        lines.extend(["", f'▶ <a href="{detail["video_url"]}">Watch Trailer</a>'])

    tags = list(set(enrich.get("genre_tags", [])))
    if detail and detail.get("tags"):
        for t in detail["tags"][:3]:
            if t not in tags:
                tags.append(t)
    tag_str = _tags_to_hashtags(tags)
    lines.extend(["", SEP, tag_str])

    return {"type": "game", "text": "\n".join(lines)}


def format_classic_gdc(session, detail, summary):
    """Feed 3: Classic GDC talk review."""
    title = detail.get("title") or session["title_from_slug"]
    url = session["url"]
    year = session.get("year", summary.get("year", ""))
    category = summary.get("category", "Other")
    category_cn = {"Programming": "编程技术", "Design": "游戏设计",
                   "Art": "美术视觉", "Production": "制作管理",
                   "Business": "商业市场"}.get(category, "综合")

    lines = [
        f'📚 <b>{_esc(title)}</b>',
        f'🟡 #经典回顾  #GDC{year}  #{_esc(category_cn)}',
        "",
        f'🔗 <a href="{url}">Watch on GDC Vault</a>',
    ]

    if summary.get("core_insight"):
        lines.extend(["", f'💡 <b>{_esc(summary["core_insight"])}</b>'])

    if summary.get("summary_cn"):
        lines.extend(["", f"<u>📌 中文梗概</u>", _bold_markers(summary["summary_cn"])])

    if summary.get("key_points"):
        lines.append("")
        lines.append("<u>🔑 核心要点</u>")
        for p in summary["key_points"]:
            lines.append(f"  • {_esc(p)}")

    tags = list(summary.get("tags", []))
    audience = _esc(summary.get("target_audience", "游戏开发者"))
    tag_str = _tags_to_hashtags(tags)
    lines.extend(["", SEP, f"⭐ {audience}  {tag_str}"])

    return {"type": "classic", "text": "\n".join(lines)}