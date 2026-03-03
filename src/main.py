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

# Ajuste realista de mercado
LIMITS = {
    13: 33000,  # R$ 330
    14: 42000,  # R$ 420
    15: 48000,  # R$ 480
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
    debug_lines: List[str] = []

    for aro, measures in MEASURES.items():
        for m in measures:
            query = f"pneu {m} preço"

            try:
                deals = serpapi_shopping(query, SERPAPI_KEY)
            except Exception as e:
                debug_lines.append(f"[ERRO] SerpAPI: {e}")
                continue

            debug_lines.append(f"\nAro {aro} — {m}")

            for d in deals:
    title_upper = d["title"].upper()

    # 1️⃣ Ignorar kits
    if any(x in title_upper for x in ["KIT", "JOGO", "4 PNEUS", "2 PNEUS"]):
        continue

    # 2️⃣ Exigir que contenha a medida exata buscada
    if m.upper() not in title_upper:
        continue

    aro_found = aro

    debug_lines.append(
        f"- {d['title']} | {format_price(d['price_cents'])}"
    )

    if d["price_cents"] <= LIMITS[aro_found]:
        if upsert_deal(conn, d):
            d2 = dict(d)
            d2["title"] = f"{d2['title']} (aro {aro_found})"
            new_items.append(d2)
    if new_items:
        lines = [f"Promoções encontradas: {len(new_items)}"]
        for d in new_items:
            lines.append(
                f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}"
            )
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
        return

    # Se não encontrou promo, manda diagnóstico
    send_telegram_message(
        BOT_TOKEN,
        CHAT_ID,
        "DEBUG — preços atuais encontrados:\n" + "\n".join(debug_lines[:40])
    )

if __name__ == "__main__":
    run()
