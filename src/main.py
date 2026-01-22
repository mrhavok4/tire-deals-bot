import os
import re
from typing import Optional, Dict, Any, List

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.scraper import scrape_pneustore, scrape_pneufree, scrape_magalu, polite_sleep

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

LIMITS = {13: 20000, 14: 26000, 15: 29000}
AROS = [13, 14, 15]
DB_PATH = "tirebot.sqlite"

def detect_aro(text: str) -> Optional[int]:
    t = text.lower()
    for a in AROS:
        if f"r{a}" in t or f"aro {a}" in t:
            return a
    return None

def format_price(cents: int) -> str:
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def run():
    conn = connect(DB_PATH)
    new_items: List[Dict[str, Any]] = []

    for aro in AROS:
        query = f"pneu aro {aro}"

        for scraper in (scrape_pneustore, scrape_pneufree, scrape_magalu):
            deals = scraper(query)
            for d in deals:
                aro_found = detect_aro(d["title"])
                if aro_found != aro:
                    continue
                if d["price_cents"] > LIMITS[aro]:
                    continue
                if upsert_deal(conn, d):
                    d["title"] += f" (aro {aro})"
                    new_items.append(d)
            polite_sleep()

    if new_items:
        lines = [f"Promoções encontradas: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(
                f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}"
            )
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
