import os
import re
from typing import Optional, Dict, Any, List

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.scraper import scrape_pneustore, scrape_pneufree, scrape_magalu, polite_sleep

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

LIMITS = {13: 20000, 14: 26000, 15: 29000}  # centavos
DB_PATH = "tirebot.sqlite"

# Medidas comuns (ajustáveis) para aumentar recall
MEASURES = {
    13: ["175/70 R13", "165/70 R13", "165/80 R13"],
    14: ["175/65 R14", "185/60 R14", "165/70 R14"],
    15: ["185/65 R15", "195/55 R15", "195/65 R15", "185/60 R15"],
}

UNWANTED = ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"]

def detect_aro(text: str) -> Optional[int]:
    t = (text or "").lower()
    m = re.search(r"\br\s*(13|14|15)\b", t)
    return int(m.group(1)) if m else None

def looks_like_kit(title: str) -> bool:
    t = (title or "").lower()
    return any(w in t for w in UNWANTED)

def format_price(cents: int) -> str:
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def run():
    conn = connect(DB_PATH)
    new_items: List[Dict[str, Any]] = []

    total_scanned = 0
    total_candidates = 0

    for aro, queries in MEASURES.items():
        for q in queries:
            query = f"pneu {q}"

            for scraper in (scrape_pneustore, scrape_pneufree, scrape_magalu):
                try:
                    deals = scraper(query)
                except Exception:
                    deals = []

                total_scanned += 1
                total_candidates += len(deals)

                for d in deals:
                    title = d.get("title", "")
                    price = d.get("price_cents")

                    if price is None:
                        continue

                    # evita kit/jogo
                    if looks_like_kit(title):
                        continue

                    aro_found = detect_aro(title)
                    if aro_found != aro:
                        continue

                    if price > LIMITS[aro]:
                        continue

                    if upsert_deal(conn, d):
                        dd = dict(d)
                        dd["title"] = f"{title[:180]} (aro {aro})"
                        new_items.append(dd)

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
