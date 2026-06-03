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