"""Telegram notification — HTML-formatted messages for daily digest."""
import os
import re

import requests

API_BASE = "https://api.telegram.org/bot"


def _get_credentials():
    token = os.environ.get("GDC_TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("GDC_TELEGRAM_CHAT_ID", "")
    return token, chat_id


def _escape_html(text):
    """Escape HTML special chars except those we explicitly format."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _send_message(html_text, disable_notification=False):
    """Send a single HTML-formatted message to Telegram. Returns True on success."""
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        print("telegram: token or chat_id not set, skipping")
        return False

    try:
        resp = requests.post(
            f"{API_BASE}{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": html_text,
                "parse_mode": "HTML",
                "disable_notification": disable_notification,
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
            # Small delay between messages to maintain order and avoid rate limits
            import time
            time.sleep(0.5)
        _send_message(msg)

    print(f"Telegram: {len(all_messages)} messages sent")


def format_gdc_talk(session, detail, summary):
    """Feed 1: Format a new GDC Vault talk for Telegram."""
    title = _escape_html(detail.get("title") or session["title_from_slug"])
    url = session["url"]
    category_cn = {
        "Programming": "编程技术", "Design": "游戏设计", "Art": "美术视觉",
        "Production": "制作管理", "Business": "商业市场",
    }.get(summary.get("category", "Other"), "综合")

    lines = [
        f'🎮 <b>GDC {session["year"]} · {category_cn}</b>',
        "",
        f'<a href="{url}">{title}</a>',
    ]

    if summary.get("one_liner"):
        lines.append("")
        lines.append(f'💡 <i>{_escape_html(summary["one_liner"])}</i>')

    if summary.get("summary_cn"):
        lines.append("")
        lines.append(f'📌 <b>中文梗概</b>')
        lines.append(_escape_html(summary["summary_cn"]))

    if summary.get("key_points"):
        lines.append("")
        lines.append("🔑 <b>核心要点</b>")
        for p in summary["key_points"]:
            lines.append(f"• {_escape_html(p)}")

    tags_line = []
    if summary.get("tags"):
        tags_line.extend(_escape_html(t) for t in summary["tags"])
    if summary.get("level"):
        tags_line.append(f"⭐ {_escape_html(summary['level'])}")
    if tags_line:
        lines.append("")
        lines.append(" · ".join(tags_line))

    return "\n".join(lines)


def format_game_release(item, detail, enrich):
    """Feed 2: Format a new game release for Telegram."""
    title = _escape_html(item["title"])
    url = item["url"]
    source = item.get("source", "Steam")

    lines = [
        f'🎮 <b>新游戏发布 · {source}</b>',
        "",
        f'<a href="{url}">{title}</a>',
    ]

    if enrich.get("one_liner_cn"):
        lines.append("")
        lines.append(f'💡 <i>{_escape_html(enrich["one_liner_cn"])}</i>')

    meta = []
    if enrich.get("genre_tags"):
        meta.append(" · ".join(_escape_html(t) for t in enrich["genre_tags"]))
    if enrich.get("platforms"):
        meta.append("🖥️ " + " · ".join(_escape_html(p) for p in enrich["platforms"]))
    if enrich.get("release_date"):
        meta.append(f'📅 {_escape_html(enrich["release_date"])}')
    if meta:
        lines.append("")
        lines.append("\n".join(meta))

    if detail and detail.get("metacritic"):
        mc = detail["metacritic"]
        lines.append(f'🎯 <b>Metacritic: {mc["score"]}</b> ({mc.get("reviews", 0)} reviews)')

    if detail and detail.get("price"):
        price_text = f'💰 {detail["price"]}'
        if detail.get("discount"):
            price_text += f' (-{detail["discount"]})'
        lines.append(price_text)

    if enrich.get("notability"):
        lines.append("")
        lines.append(f'📝 {_escape_html(enrich["notability"])}')

    if detail and detail.get("video_url"):
        lines.append("")
        lines.append(f'▶ <a href="{detail["video_url"]}">Watch Trailer</a>')

    return "\n".join(lines)


def format_classic_gdc(session, detail, summary):
    """Feed 3: Format a classic GDC talk review for Telegram."""
    title = _escape_html(detail.get("title") or session["title_from_slug"])
    url = session["url"]
    year = session.get("year", summary.get("year", ""))
    category = summary.get("category", "Other")
    category_cn = {
        "Programming": "编程技术", "Design": "游戏设计", "Art": "美术视觉",
        "Production": "制作管理", "Business": "商业市场",
    }.get(category, "综合")

    lines = [
        f'📚 <b>经典回顾 · GDC {year}</b>',
        "",
        f'<b>【{category_cn}】</b> <a href="{url}">{title}</a>',
    ]

    if summary.get("core_insight"):
        lines.append("")
        # HTML bold inside the insight
        insight = _escape_html(summary["core_insight"])
        lines.append(f'💡 <b>{insight}</b>')

    if summary.get("summary_cn"):
        lines.append("")
        lines.append(f'📌 <b>中文梗概</b>')
        # summary_cn may contain **bold** markers, convert to HTML <b>
        cn_text = summary["summary_cn"]
        # First escape, then convert markdown bold to HTML bold
        cn_text = _escape_html(cn_text)
        cn_text = re.sub(r'&lt;b&gt;(.+?)&lt;/b&gt;', r'<b>\1</b>', cn_text)
        # Also handle ** markers (need to do before escaping or we handle them separately)
        cn_text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', cn_text)
        lines.append(cn_text)

    if summary.get("key_points"):
        lines.append("")
        lines.append("🔑 <b>核心要点</b>")
        for p in summary["key_points"]:
            lines.append(f"• {_escape_html(p)}")

    if summary.get("tags"):
        lines.append("")
        lines.append(" · ".join(_escape_html(t) for t in summary["tags"]))

    audience = summary.get("target_audience", "游戏开发者")
    lines.append(f'⭐ {_escape_html(audience)} · GDC {year}')

    return "\n".join(lines)