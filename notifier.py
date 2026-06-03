"""Discord embed formatting and webhook delivery."""
import os

import requests

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
        "title": detail.get("title") or session["title_from_slug"],
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
    webhook_url = os.environ.get("GDC_WEBHOOK_URL", "")
    if not webhook_url:
        print("GDC_WEBHOOK_URL not set, skipping Discord send")
        return

    for i in range(0, len(embeds), 10):
        batch = embeds[i : i + 10]
        try:
            resp = requests.post(webhook_url, json={"embeds": batch}, timeout=30)
            resp.raise_for_status()
            print(f"Sent {len(batch)} embed(s) to Discord")
        except requests.RequestException as e:
            print(f"Failed to send batch {i // 10 + 1}: {e}")


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
    if meta_parts:
        desc_parts.append("\n".join(meta_parts))

    embed = {
        "author": {"name": f'🎮 新游戏发布 · {item.get("source", "Steam")}'},
        "title": item["title"],
        "url": item["url"],
        "description": "\n".join(desc_parts),
        "color": 0x2ECC71,
        "footer": {"text": "GDC Daily Digest · 新游戏发布"},
    }

    if detail and detail.get("image"):
        embed["thumbnail"] = {"url": detail["image"]}

    if detail and detail.get("metacritic"):
        mc = detail["metacritic"]
        embed["description"] += f'\n\n🎯 **Metacritic: {mc["score"]}** ({mc.get("reviews", 0)} reviews)'

    if detail and detail.get("price"):
        price_text = f'💰 {detail["price"]}'
        if detail.get("discount"):
            price_text += f' (-{detail["discount"]})'
        embed["description"] += f'\n{price_text}'

    if detail and detail.get("video_url"):
        if "description" in embed:
            embed["description"] += f'\n\n▶ [Watch Trailer]({detail["video_url"]})'
        else:
            embed["description"] = f'▶ [Watch Trailer]({detail["video_url"]})'

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
        "color": 0xF39C12,
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