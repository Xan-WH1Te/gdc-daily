"""GDC Vault HTML scraping — session list + og meta tags."""
import re
import time
from urllib.parse import urljoin

import requests

BASE_URL = "https://gdcvault.com"
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = "GDC-Daily/1.0"
    return _session


def fetch_year_sessions(year):
    """Return list of {session_id, url, title_from_slug, year} from a year page."""
    short = str(year)[-2:]
    url = f"{BASE_URL}/free/gdc-{short}/"
    resp = _get_session().get(url, timeout=30)
    resp.raise_for_status()

    sessions = []
    seen = set()
    for m in re.finditer(r'href="(/play/(\d+)/([^"]*))"', resp.text):
        path, sid, slug = m.group(1), m.group(2), m.group(3)
        if sid in seen:
            continue
        seen.add(sid)
        title = slug.replace("-", " ").strip() if slug else f"Session {sid}"
        sessions.append({
            "session_id": sid,
            "url": urljoin(BASE_URL, path),
            "title_from_slug": title,
            "year": str(year),
        })
    return sessions


def _get_meta(text, prop):
    m = re.search(rf'<meta\s+property="og:{prop}"\s+content="([^"]*)"', text)
    return m.group(1) if m else ""


def fetch_session_detail(url, retries=3):
    """Return {title, description, image} from a session page. Retries on failure."""
    s = _get_session()
    for attempt in range(retries):
        try:
            resp = s.get(url, timeout=30)
            if resp.status_code in (404, 403):
                return None
            resp.raise_for_status()
            return {
                "title": _get_meta(resp.text, "title"),
                "description": _get_meta(resp.text, "description"),
                "image": _get_meta(resp.text, "image"),
            }
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    return None