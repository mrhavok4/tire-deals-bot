import os
import re
from typing import Dict, Any, List

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.serpapi import serpapi_shopping

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SERPAPI_KEY = os.environ["SERPAPI_KEY"]

DB_PATH = "tirebot.sqlite"

LIMITS = {
    13: 30000,  # R$ 300
    14: 38000,  # R$ 380
    15: 45000,  # R$ 450
}

MEASURES = {
    13: ["175/70 R13", "165/70 R13"],
    14: ["175/65 R14", "185/60 R14"],
    15: ["185/65 R15", "195/55 R15"],
}

def detect_aro(text: str):
    m = re.search(r"\bR\s*(13|14|15)\b", (text or "").upper())
    return int(m.group(1)) if m else None

def format_price(cents: int) -> str:
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def run():
    conn = connect(DB_PATH)
    new_items: List[Dict[str, Any]] = []

    for aro, measures in MEASURES.items():
        for m in measures:
            query = f"pneu {m} preço"
            try:
                deals = serpapi_shopping(query, SERPAPI_KEY)
            except Exception as e:
                print(f"[WARN] SerpAPI error: {e}")
                continue

            for d in deals:
                aro_found = detect_aro(d["title"]) or aro
                if aro_found not in LIMITS:
                    continue

                if d["price_cents"] <= LIMITS[aro_found]:
                    if upsert_deal(conn, d):
                        d2 = dict(d)
                        d2["title"] = f"{d2['title']} (aro {aro_found})"
                        new_items.append(d2)

    if new_items:
        lines = [f"Promoções encontradas: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(
                f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}"
            )
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
        return

    send_telegram_message(
        BOT_TOKEN,
        CHAT_ID,
        "TireBot: execução OK. Nenhuma promoção dentro dos limites."
    )

if __name__ == "__main__":
    run()
