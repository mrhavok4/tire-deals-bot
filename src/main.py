import os
from typing import Dict, Any, List
from collections import defaultdict

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.rss_bing import (
    fetch_bing_rss, price_from_text_cents, detect_aro,
    looks_like_kit, looks_unavailable, polite_sleep
)
from src.shopee import scrape_shopee

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
DB_PATH = "tirebot.sqlite"

LIMITS = {13: 20000, 14: 26000, 15: 29000}

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
    stats = defaultdict(int)

    # 1) Bing RSS (nível Google)
    for aro, measures in MEASURES.items():
        for m in measures:
            q = f"pneu {m} preço"
            try:
                items = fetch_bing_rss(q)
            except Exception as e:
                print(f"[WARN] Bing RSS error: {e}")
                continue

            for it in items[:20]:
                txt = f"{it['title']} {it.get('desc','')}"
                if looks_like_kit(txt) or looks_unavailable(txt):
                    continue

                price = price_from_text_cents(txt)
                if price is None or price < 10000:
                    continue

                aro_found = detect_aro(txt) or aro
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

                if price <= LIMITS[aro_found]:
                    if upsert_deal(conn, deal):
                        deal["title"] = f"{deal['title']} (aro {aro_found})"
                        new_items.append(deal)

            polite_sleep()

    # 2) Shopee
    for aro, measures in MEASURES.items():
        for m in measures:
            q = f"pneu {m.replace('/',' ')}"
            deals = scrape_shopee(q)
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

    if new_items:
        lines = [f"Promoções dentro do limite: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}")
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
        return

    lines = ["TireBot: sem resultados dentro dos limites.", "TOP mais baratos por aro (referência):"]
    for aro in (13, 14, 15):
        lines.append(f"\nAro {aro} (limite {format_price(LIMITS[aro])}):")
        top = top_by_aro[aro]
        if not top:
            lines.append("- (nenhum item detectado)")
            continue
        for it in top[:10]:
            lines.append(f"- [{it['source']}] {it['title']} | {format_price(it['price_cents'])}\n  {it['url']}")
    send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))

if __name__ == "__main__":
    run()
