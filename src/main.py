import os
from typing import Dict, Any, List, DefaultDict
from collections import defaultdict

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.scraper import (
    scrape_mercadolivre,
    scrape_shopee,
    polite_sleep,
    parse_measure,
    detect_aro,
    looks_like_kit,
    normalize_url,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
DB_PATH = "tirebot.sqlite"

LIMITS = {13: 20000, 14: 26000, 15: 29000}  # centavos

MEASURES = {
    13: ["175/70 R13", "165/70 R13", "165/80 R13"],
    14: ["175/65 R14", "185/60 R14", "165/70 R14"],
    15: ["185/65 R15", "195/55 R15", "195/65 R15", "185/60 R15"],
}

def format_price(cents: int) -> str:
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def _push_topn(topn: List[Dict[str, Any]], item: Dict[str, Any], n: int = 10):
    topn.append(item)
    topn.sort(key=lambda x: x["price_cents"])
    del topn[n:]

def run():
    conn = connect(DB_PATH)

    new_items: List[Dict[str, Any]] = []
    top_by_aro = {13: [], 14: [], 15: []}

    stats: DefaultDict[str, int] = defaultdict(int)
    total_candidates = 0

    for aro, measures in MEASURES.items():
        for measure in measures:
            pm = parse_measure(measure)
            q = f"pneu {pm['largura']} {pm['altura']} r{pm['aro']}" if pm else f"pneu {measure}"

            for fn, label in (
                (scrape_mercadolivre, "MercadoLivre"),
                (scrape_shopee, "Shopee"),
            ):
                try:
                    deals = fn(q)
                except Exception as e:
                    print(f"[WARN] scraper error {label}: {e}")
                    deals = []

                stats[label] += len(deals)
                total_candidates += len(deals)

                for d in deals:
                    title = d.get("title", "")
                    url = normalize_url(d.get("url", ""))
                    price = d.get("price_cents")

                    if not title or not url or price is None:
                        continue
                    if looks_like_kit(title):
                        continue

                    aro_found = detect_aro(title) or aro
                    if aro_found not in (13, 14, 15):
                        continue

                    # top barato sempre
                    _push_topn(top_by_aro[aro_found], {
                        "source": d.get("source", label),
                        "title": title[:160],
                        "url": url,
                        "price_cents": price,
                    }, n=10)

                    # filtro do limite
                    if price <= LIMITS[aro_found]:
                        d2 = dict(d)
                        d2["url"] = url
                        if upsert_deal(conn, d2):
                            d2["title"] = f"{title[:180]} (aro {aro_found})"
                            new_items.append(d2)

                polite_sleep()

    if new_items:
        lines = [f"Promoções dentro do limite: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}")
        if len(new_items) > 20:
            lines.append(f"(+{len(new_items)-20} itens)")
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
        return

    lines = [
        "TireBot: sem resultados dentro dos limites.",
        f"Itens lidos: {total_candidates} (ML={stats['MercadoLivre']}, Shopee={stats['Shopee']}).",
        "TOP mais baratos por aro (para calibrar):",
    ]
    for aro in (13, 14, 15):
        lines.append(f"\nAro {aro} (limite atual {format_price(LIMITS[aro])}):")
        top = top_by_aro[aro]
        if not top:
            lines.append("- (nenhum item detectado)")
            continue
        for it in top[:10]:
            lines.append(f"- [{it['source']}] {it['title']} | {format_price(it['price_cents'])}\n  {it['url']}")
    send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))

if __name__ == "__main__":
    run()
