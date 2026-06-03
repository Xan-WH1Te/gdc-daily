"""Feed 3: Classic GDC talk review — seed library + daily rotation."""
import json
import os
import random
import sqlite3

SEEDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "classic_seeds.json",
)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "classic_state.db",
)


def load_seeds():
    """Load classic talk seeds from JSON file."""
    if not os.path.exists(SEEDS_PATH):
        return []
    with open(SEEDS_PATH) as f:
        return json.load(f)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shown_classics (
            talk_id TEXT PRIMARY KEY,
            shown_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def pick_daily(seeds):
    """Pick 1-2 unseen classic talks for today. Rotates through all seeds."""
    if not seeds:
        return []

    conn = init_db()
    shown = set()
    for row in conn.execute("SELECT talk_id FROM shown_classics"):
        shown.add(row[0])

    unseen = [s for s in seeds if s.get("id") not in shown]

    # If all shown, reset for new cycle
    if not unseen:
        conn.execute("DELETE FROM shown_classics")
        conn.commit()
        unseen = seeds[:]

    count = min(random.randint(1, 2), len(unseen))
    picked = random.sample(unseen, count)

    for s in picked:
        conn.execute(
            "INSERT OR IGNORE INTO shown_classics (talk_id) VALUES (?)",
            (s["id"],),
        )
    conn.commit()
    conn.close()
    return picked


def add_seed(talk):
    """Append a new talk to the seed library."""
    seeds = load_seeds()
    for s in seeds:
        if s["id"] == talk["id"]:
            return
    seeds.append(talk)
    with open(SEEDS_PATH, "w") as f:
        json.dump(seeds, f, ensure_ascii=False, indent=2)