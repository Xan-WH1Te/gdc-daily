"""Telegram notification — HTML-formatted messages for daily digest."""
import os
import re
import time

import requests

API_BASE = "https://api.telegram.org/bot"
SEP = "━━━━━━━━━━━━━━━━━━━━━━"


def _get_credentials():
    token = os.environ.get("GDC_TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("GDC_TELEGRAM_CHAT_ID", "")
    return token, chat_id


def _esc(text):
    """Escape HTML special chars."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bold_markers(text):
    """Convert **markers** to <b>HTML</b> after escaping."""
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text


def _tags_to_hashtags(tags):
    """Convert tags list to clickable Telegram hashtags."""
    if not tags:
        return ""
    return "  ".join(f"#{_esc(t).replace(' ', '_')}" for t in tags if t)


def _send_message(html_text):
    """Send a single HTML-formatted message to Telegram."""
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"{API_BASE}{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": html_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"telegram: send failed: {e}")
        return False


def send_digest(all_messages):
    """Send all digest messages to Telegram, one per talk/item."""
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        print("GDC_TELEGRAM_TOKEN or GDC_TELEGRAM_CHAT_ID not set, skipping Telegram")
        return

    if not all_messages:
        return

    print(f"Sending {len(all_messages)} messages to Telegram...")
    for i, msg in enumerate(all_messages):
        if i > 0:
            time.sleep(0.4)
        _send_message(msg)

    print(f"Telegram: {len(all_messages)} messages sent")


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
        lines.extend(["", f'<u>📌 中文梗概</u>', _esc(summary["summary_cn"])])

    if summary.get("key_points"):
        lines.append("")
        lines.append("<u>🔑 核心要点</u>")
        for p in summary["key_points"]:
            lines.append(f"  • {_esc(p)}")

    tags = _tags_to_hashtags(summary.get("tags", []))
    level_str = {"Beginner": "入门", "Intermediate": "进阶", "Advanced": "深入"}
    level = level_str.get(summary.get("level", ""), "")
    footer = f'⭐ {_esc(level)}' if level else ""
    lines.extend(["", SEP, f"{tags}  {footer}".strip()])

    return "\n".join(lines)


def format_game_release(item, detail, enrich):
    """Feed 2: New game release."""
    title = item["title"]
    url = item["url"]
    source = item.get("source", "Steam")
    name_cn = detail.get("name_cn", "") if detail else ""

    display_title = f"{_esc(name_cn)} / {_esc(title)}" if name_cn else _esc(title)

    lines = [
        f'🎮 <b>{display_title}</b>',
        f'🟢 #{_esc(source)}  #新游戏发布',
        "",
        f'🔗 <a href="{url}">Store Page</a>',
    ]

    if enrich.get("one_liner_cn"):
        lines.extend(["", f'💡 <i>{_esc(enrich["one_liner_cn"])}</i>'])

    # Meta line
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

    # Metacritic + Price on same line
    stats = []
    if detail and detail.get("metacritic"):
        mc = detail["metacritic"]
        stats.append(f'🎯 <b>{mc["score"]}</b> ({mc.get("reviews", 0)} reviews)')
    if detail and detail.get("price"):
        price_str = f'💰 {detail["price"]}'
        if detail.get("discount"):
            price_str += f' <s>{detail.get("og_price", "")}</s>'
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

    return "\n".join(lines)


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
        lines.extend(["", f'<u>📌 中文梗概</u>', _bold_markers(summary["summary_cn"])])

    if summary.get("key_points"):
        lines.append("")
        lines.append("<u>🔑 核心要点</u>")
        for p in summary["key_points"]:
            lines.append(f"  • {_esc(p)}")

    tags = list(summary.get("tags", []))
    audience = _esc(summary.get("target_audience", "游戏开发者"))
    tag_str = _tags_to_hashtags(tags)
    lines.extend(["", SEP, f'⭐ {audience}  {tag_str}'])

    return "\n".join(lines)