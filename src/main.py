import os
from typing import Optional, Dict, Any, List

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.scraper import scrape_pneustore, scrape_pneufree, scrape_magalu, polite_sleep

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

LIMITS = {13: 20000, 14: 26000, 15: 29000}  # centavos
AROS = [13, 14, 15]
DB_PATH = "tirebot.sqlite"

def detect_aro(text: str) -> Optional[int]:
    t = (text or "").lower()
    for a in AROS:
        if f"r{a}" in t or f"aro {a}" in t or f"aro{a}" in t:
            return a
    return None

def format_price(cents: int) -> str:
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def run():
    conn = connect(DB_PATH)
    new_items: List[Dict[str, Any]] = []

    total_scanned = 0
    total_candidates = 0

    for aro in AROS:
        query = f"pneu aro {aro}"

        for scraper in (scrape_pneustore, scrape_pneufree, scrape_magalu):
            try:
                deals = scraper(query)
            except Exception:
                deals = []

            total_scanned += 1
            total_candidates += len(deals)

            for d in deals:
                aro_found = detect_aro(d.get("title", ""))
                if aro_found != aro:
                    continue

                price = d.get("price_cents")
                if price is None:
                    continue
                if price > LIMITS[aro]:
                    continue

                if upsert_deal(conn, d):
                    d = dict(d)
                    d["title"] = f"{d.get('title','')[:180]} (aro {aro})"
                    new_items.append(d)

            polite_sleep()

    if new_items:
        lines = [f"Promoções encontradas: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(
                f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}"
            )
        if len(new_items) > 20:
            lines.append(f"(+{len(new_items)-20} itens)")
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
    else:
        send_telegram_message(
            BOT_TOKEN,
            CHAT_ID,
            f"TireBot: execução OK. Consultas: {total_scanned}. Itens lidos: {total_candidates}. Sem resultados dentro dos limites."
        )

if __name__ == "__main__":
    run()
