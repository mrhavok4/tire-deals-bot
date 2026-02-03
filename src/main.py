import os
from typing import Dict, Any, List
from collections import defaultdict

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.rss_bing import (
    fetch_bing_rss,
    price_from_text_cents,
    detect_aro,
    looks_like_kit,
    looks_unavailable,
    polite_sleep,
)
from src.shopee import scrape_shopee

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
DB_PATH = "tirebot.sqlite"

LIMITS = {13: 20000, 14: 26000, 15: 29000}  # centavos

MEASURES = {
    13: ["175/70 R13", "165/70 R13", "165/80 R13"],
    14: ["175/65 R14", "185/60 R14", "165/70 R14"],
    15: ["185/65 R15", "195/55 R15", "195/65 R15", "185/60 R15"],
}

def format_price(cents: int | None) -> str:
    if cents is None:
        return "Preço não identificado"
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def _push_topn(topn: List[Dict[str, Any]], item: Dict[str, Any], n: int = 10):
    topn.append(item)
    topn.sort(key=lambda x: (x["price_cents"] is None, x["price_cents"] or 10**12))
    del topn[n:]

def run():
    conn = connect(DB_PATH)

    new_items: List[Dict[str, Any]] = []
    top_by_aro = {13: [], 14: [], 15: []}
    stats = defaultdict(int)

    # =======================
    # 1) Bing RSS (descoberta)
    # =======================
    for aro, measures in MEASURES.items():
        for m in measures:
            query = f"pneu {m} promoção preço"
            try:
                items = fetch_bing_rss(query)
            except Exception as e:
                print(f"[WARN] Bing RSS error: {e}")
                continue

            stats["BingRSS"] += len(items)

            for it in items[:20]:
                text = f"{it['title']} {it.get('desc','')}"
                if looks_like_kit(text) or looks_unavailable(text):
                    continue

                price = price_from_text_cents(text)  # pode ser None
                aro_found = detect_aro(text) or aro

                deal = {
                    "source": "BingRSS",
                    "title": it["title"][:180],
                    "url": it["url"],
                    "price_cents": price,
                }

                _push_topn(top_by_aro[aro_found], {
                    "source": deal["source"],
                    "title": deal["title"][:160],
                    "url": deal["url"],
                    "price_cents": deal["price_cents"],
                })

                # só aplica limite se houver preço
                if price is not None and price <= LIMITS[aro_found]:
                    if upsert_deal(conn, deal):
                        deal["title"] = f"{deal['title']} (aro {aro_found})"
                        new_items.append(deal)

            polite_sleep()

    # =======================
    # 2) Shopee (API direta)
    # =======================
    for aro, measures in MEASURES.items():
        for m in measures:
            query = f"pneu {m.replace('/',' ')}"
            try:
                deals = scrape_shopee(query)
            except Exception as e:
                print(f"[WARN] Shopee error: {e}")
                deals = []

            stats["Shopee"] += len(deals)

            for d in deals:
                price = d["price_cents"]
                aro_found = detect_aro(d["title"]) or aro

                _push_topn(top_by_aro[aro_found], {
                    "source": d["source"],
                    "title": d["title"][:160],
                    "url": d["url"],
                    "price_cents": price,
                })

                if price <= LIMITS[aro_found]:
                    if upsert_deal(conn, d):
                        d2 = dict(d)
                        d2["title"] = f"{d2['title']} (aro {aro_found})"
                        new_items.append(d2)

            polite_sleep()

    # =======================
    # Saída / Telegram
    # =======================
    if new_items:
        lines = [f"Promoções dentro do limite: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(
                f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}"
            )
        if len(new_items) > 20:
            lines.append(f"(+{len(new_items)-20} itens)")
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
        return

    lines = [
        "TireBot: nenhuma promoção dentro dos limites.",
        f"Leituras: BingRSS={stats['BingRSS']} | Shopee={stats['Shopee']}",
        "TOP itens detectados por aro:",
    ]

    for aro in (13, 14, 15):
        lines.append(f"\nAro {aro} (limite {format_price(LIMITS[aro])}):")
        top = top_by_aro[aro]
        if not top:
            lines.append("- (nenhum item detectado)")
            continue
        for it in top[:10]:
            lines.append(
                f"- [{it['source']}] {it['title']} | {format_price(it['price_cents'])}\n  {it['url']}"
            )

    send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))

if __name__ == "__main__":
    run()
