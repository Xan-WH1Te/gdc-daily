"""AI summarization via OpenAI-compatible API — structured JSON from GDC talk descriptions."""
import json
import os
import re

import requests

# OpenAI-compatible endpoint (Alibaba Cloud / DeepSeek)
API_BASE = os.environ.get("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL = os.environ.get("OPENAI_MODEL", "deepseek-chat")

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
    """Return structured summary dict from AI API. Falls back gracefully on errors."""
    if not description or not description.strip():
        return _fallback(title)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("summarizer: ANTHROPIC_API_KEY not set, using fallback")
        return _fallback(title)

    try:
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 500,
                "temperature": 0.3,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a game development technical editor. Always output valid JSON.",
                    },
                    {
                        "role": "user",
                        "content": PROMPT.format(description=description),
                    },
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"summarizer: API call failed: {e}, using fallback")
        return _fallback(title)

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