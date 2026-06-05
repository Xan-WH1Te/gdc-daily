"""AI summarization via OpenAI-compatible API — structured JSON from GDC talk descriptions."""
import json
import os
import re

import requests

API_BASE = os.environ.get("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL = os.environ.get("OPENAI_MODEL", "deepseek-v4-flash")

GDC_PROMPT = """You are a game development technical editor. Based on the GDC talk description below, output ONLY a JSON object (no markdown fences, no extra text) with these exact fields:

{{
  "one_liner": "Most impactful insight/conclusion from this talk, in Chinese, within 20 characters",
  "summary_cn": "2-3 sentence Chinese summary covering: background problem → approach/method → conclusion/value",
  "key_points": ["Key takeaway 1 in English", "Key takeaway 2", "Key takeaway 3"],
  "tags": ["tag1", "tag2", "tag3"],
  "level": "Beginner | Intermediate | Advanced",
  "category": "Programming | Design | Art | Production | Business | Other"
}}

Talk description:
{description}"""

GAME_FILTER_PROMPT = """You are a game industry editor for Chinese developers.
From this list of recent game releases and news, pick 2-4 items that are MOST noteworthy.

Criteria: AAA sequels, known studios, innovative gameplay, high buzz,
major publisher events (Sony/Nintendo/Microsoft), Chinese community interest.

Items:
{catalog}

Output ONLY a JSON array of selected indices, e.g. [0, 3, 5]"""

GAME_ENRICH_PROMPT = """For this game, output a JSON object:
{{
  "one_liner_cn": "Chinese one-liner capturing what makes this game exciting (within 20 chars). Use the provided official Chinese name for the game, DO NOT invent translations for game titles, character names, or proper nouns",
  "genre_tags": ["genre1", "genre2"],
  "platforms": ["PC", "PS5"],
  "release_date": "YYYY-MM-DD or empty string if unknown",
  "notability": "Brief reason why this matters (Chinese, 1 sentence). Keep game names and character names in their original English form if no official Chinese translation exists."
}}

Official Chinese name (from Steam/IGN, empty if none): {name_cn}
Game: {title}
Description: {description}"""

CLASSIC_PROMPT = """You are a game development educator. This is a classic GDC talk from {year}.
Write a review-style summary for today's developers.

Talk: {title}
Description: {description}

Output ONLY a JSON object:
{{
  "core_insight": "The single most important idea from this talk, in Chinese (bold-worthy, within 30 chars)",
  "summary_cn": "2-3 sentence Chinese summary. Use **bold** markdown around key concepts, methodology names, and important terminology",
  "key_points": ["English key takeaway 1", "English key takeaway 2", "English key takeaway 3"],
  "tags": ["tag1", "tag2", "tag3"],
  "target_audience": "Who should watch this (Chinese, e.g. 关卡策划 · 独立开发者)",
  "category": "Programming | Design | Art | Production | Business | Other"
}}"""


def _call_ai(system_prompt, user_prompt):
    """Raw AI call returning parsed JSON. Returns None on failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("summarizer: ANTHROPIC_API_KEY not set")
        return None

    try:
        resp = requests.post(
            f"{API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={
                "model": MODEL, "max_tokens": 800, "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError) as e:
        print(f"summarizer: API call failed: {e}")
        return None

    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def summarize_gdc(description, title):
    """Feed 1: Summarize a new GDC Vault talk."""
    if not description or not description.strip():
        return _fallback(title)
    result = _call_ai(
        "You are a game development technical editor. Always output valid JSON.",
        GDC_PROMPT.format(description=description),
    )
    return result if result else _fallback(title)


def summarize_game_filter(catalog_text):
    """Feed 2 filter: Given a list of game titles, return indices of noteworthy ones."""
    result = _call_ai(
        "You are a game industry editor. Output valid JSON arrays only.",
        GAME_FILTER_PROMPT.format(catalog=catalog_text),
    )
    return result if isinstance(result, list) else []


def summarize_game_enrich(title, description, name_cn=""):
    """Feed 2 enrich: Generate Chinese one-liner + metadata for a game."""
    if not description:
        return {
            "one_liner_cn": name_cn or title, "genre_tags": [],
            "platforms": [], "release_date": "", "notability": "",
        }
    result = _call_ai(
        "You are a game industry editor. Always output valid JSON.",
        GAME_ENRICH_PROMPT.format(title=title, description=description[:500], name_cn=name_cn or "Unknown"),
    )
    if result:
        result.setdefault("one_liner_cn", title)
        result.setdefault("genre_tags", [])
        result.setdefault("platforms", [])
        result.setdefault("release_date", "")
        result.setdefault("notability", "")
        return result
    return {
        "one_liner_cn": title, "genre_tags": [],
        "platforms": [], "release_date": "", "notability": "",
    }


def summarize_classic(description, title, year):
    """Feed 3: Classic GDC talk review-style summary with bold keywords."""
    if not description or not description.strip():
        return {**_fallback(title), "core_insight": title, "target_audience": "游戏开发者"}
    result = _call_ai(
        "You are a game development educator. Always output valid JSON. Use **bold** markdown around key concepts.",
        CLASSIC_PROMPT.format(description=description, title=title, year=year),
    )
    if result:
        result.setdefault("core_insight", title)
        result.setdefault("target_audience", "游戏开发者")
        return result
    return {**_fallback(title), "core_insight": title, "target_audience": "游戏开发者"}


def summarize(description, title):
    """Backward-compatible wrapper for Feed 1."""
    return summarize_gdc(description, title)


def _fallback(title):
    return {
        "one_liner": title,
        "summary_cn": "暂无简介",
        "key_points": [],
        "tags": [],
        "level": "Intermediate",
        "category": "Other",
    }