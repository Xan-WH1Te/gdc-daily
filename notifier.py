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