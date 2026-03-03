import os
from typing import Dict, Any, List

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.serpapi import serpapi_shopping

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
SERPAPI_KEY = os.environ["SERPAPI_KEY"]

DB_PATH = "tirebot.sqlite"

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

UNWANTED = ["KIT", "JOGO", "4 PNEUS", "2 PNEUS", "PAR", "COMBO"]

def format_price(cents: int) -> str:
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def _push_topn(topn: List[Dict[str, Any]], item: Dict[str, Any], n: int = 5):
    topn.append(item)
    topn.sort(key=lambda x: x["price_cents"])
    del topn[n:]

def run():
    conn = connect(DB_PATH)
    new_items: List[Dict[str, Any]] = []
    top_by_aro = {13: [], 14: [], 15: []}

    for aro, measures in MEASURES.items():
        for measure in measures:

            query = f"pneu {measure} preço"

            try:
                deals = serpapi_shopping(query, SERPAPI_KEY)
            except Exception as e:
                print(f"[ERRO] SerpAPI: {e}")
                continue

            for d in deals:
                title_upper = d["title"].upper()

                # Ignorar kits
                if any(word in title_upper for word in UNWANTED):
                    continue

                # Exigir medida exata
                if measure.upper() not in title_upper:
                    continue

                price = d["price_cents"]

                # Guardar TOP referência sempre
                _push_topn(
                    top_by_aro[aro],
                    {
                        "source": d["source"],
                        "title": d["title"][:150],
                        "url": d["url"],
                        "price_cents": price,
                    },
                )

                # Filtro de limite
                if price <= LIMITS[aro]:
                    if upsert_deal(conn, d):
                        d2 = dict(d)
                        d2["title"] = f"{d2['title']} (aro {aro})"
                        new_items.append(d2)

    # ===== Se encontrou promo =====
    if new_items:
        lines = [f"Promoções encontradas: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(
                f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}"
            )
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
        return

    # ===== Se não encontrou, envia TOP referência =====
    lines = ["TireBot: nenhuma promoção dentro dos limites.", "Referência de preços atuais:"]

    for aro in (13, 14, 15):
        lines.append(f"\nAro {aro} (limite {format_price(LIMITS[aro])}):")

        top = top_by_aro[aro]
        if not top:
            lines.append("- Nenhum item encontrado")
            continue

        for item in top:
            lines.append(
                f"- [{item['source']}] {item['title']} | {format_price(item['price_cents'])}\n  {item['url']}"
            )

    send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))


if __name__ == "__main__":
    run()
