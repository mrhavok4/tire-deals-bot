import os
import re
from typing import Optional, Dict, Any, List

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.scraper import (
    build_ml_search_url, scrape_mercadolivre,
    build_casasbahia_search_url, scrape_casasbahia,
    build_magalu_search_url, scrape_magalu,
    polite_sleep,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

DB_PATH = "tirebot.sqlite"

LIMITS = {13: 20000, 14: 26000, 15: 29000}
AROS = [13, 14, 15]

def format_price(cents: Optional[int]) -> str:
    if cents is None:
        return "Preço não identificado"
    reais = cents // 100
    cent = cents % 100
    return f"R$ {reais:,}".replace(",", ".") + f",{cent:02d}"

def detect_aro(text: str) -> Optional[int]:
    t = (text or "").lower()
    for a in AROS:
        if re.search(rf"\br\s*{a}\b", t) or re.search(rf"\baro\s*{a}\b", t):
            return a
    m = re.search(r"\br\s*(13|14|15)\b", t)
    return int(m.group(1)) if m else None

def within_limit(aro: int, price_cents: Optional[int]) -> bool:
    if price_cents is None:
        return False
    return price_cents <= LIMITS[aro]

def build_queries() -> List[str]:
    # manter simples: a detecção do aro é no título
    return [f"pneu R{a}" for a in AROS]

def run():
    conn = connect(DB_PATH)
    new_items: List[Dict[str, Any]] = []

    for q in build_queries():
        # Mercado Livre
        deals = scrape_mercadolivre(build_ml_search_url(q))
        for d in deals:
            aro = detect_aro(d["title"])
            if aro and within_limit(aro, d.get("price_cents")):
                d["title"] = f"{d['title']} (aro {aro})"
                if upsert_deal(conn, d):
                    new_items.append(d)
        polite_sleep()

        # Casas Bahia (pode vir vazio por 403)
        deals = scrape_casasbahia(build_casasbahia_search_url(q))
        for d in deals:
            aro = detect_aro(d["title"])
            if aro and within_limit(aro, d.get("price_cents")):
                d["title"] = f"{d['title']} (aro {aro})"
                if upsert_deal(conn, d):
                    new_items.append(d)
        polite_sleep()

        # Magalu
        deals = scrape_magalu(build_magalu_search_url(q))
        for d in deals:
            aro = detect_aro(d["title"])
            if aro and within_limit(aro, d.get("price_cents")):
                d["title"] = f"{d['title']} (aro {aro})"
                if upsert_deal(conn, d):
                    new_items.append(d)
        polite_sleep()

    if new_items:
        lines = [f"Pneus dentro do limite: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(
                f"- [{d['source']}] {d['title']} | {format_price(d.get('price_cents'))}\n  {d['url']}"
            )
        if len(new_items) > 20:
            lines.append(f"(+{len(new_items)-20} itens)")
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
    else:
        # opcional: comente para não enviar “sem novidades”
        send_telegram_message(BOT_TOKEN, CHAT_ID, "TireBot: execução OK. Sem pneus dentro dos limites.")

if __name__ == "__main__":
    run()
