import os
import re
from typing import Optional, Dict, Any, List, DefaultDict
from collections import defaultdict

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.scraper import scrape_pneustore, scrape_pneufree, scrape_magalu, polite_sleep

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

LIMITS = {13: 20000, 14: 26000, 15: 29000}  # centavos
DB_PATH = "tirebot.sqlite"

MEASURES = {
    13: ["175/70 R13", "165/70 R13", "165/80 R13"],
    14: ["175/65 R14", "185/60 R14", "165/70 R14"],
    15: ["185/65 R15", "195/55 R15", "195/65 R15", "185/60 R15"],
}

UNWANTED = ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"]

def detect_aro(text: str) -> Optional[int]:
    m = re.search(r"\bR\s*(13|14|15)\b", (text or "").upper())
    return int(m.group(1)) if m else None

def looks_like_kit(title: str) -> bool:
    t = (title or "").lower()
    return any(w in t for w in UNWANTED)

def format_price(cents: int) -> str:
    return f"R$ {cents//100:,}".replace(",", ".") + f",{cents%100:02d}"

def _push_topn(topn: List[Dict[str, Any]], item: Dict[str, Any], n: int = 10):
    topn.append(item)
    topn.sort(key=lambda x: x["price_cents"])
    if len(topn) > n:
        del topn[n:]

def run():
    conn = connect(DB_PATH)

    new_items: List[Dict[str, Any]] = []
    top_by_aro = {13: [], 14: [], 15: []}

    stats: DefaultDict[str, int] = defaultdict(int)   # contagem por source
    total_candidates = 0

    for aro, measures in MEASURES.items():
        for measure in measures:
            # PneuStore / PneuFree usam medida; Magalu usa texto
            for fn, arg, src in (
                (scrape_pneustore, measure, "PneuStore"),
                (scrape_pneufree, measure, "PneuFree"),
                (scrape_magalu, f"pneu {measure}", "MagazineLuiza"),
            ):
                try:
                    deals = fn(arg)
                except Exception:
                    deals = []

                stats[src] += len(deals)
                total_candidates += len(deals)

                for d in deals:
                    title = d.get("title", "")
                    price = d.get("price_cents")
                    url = d.get("url", "")

                    if not title or not url or price is None:
                        continue
                    if looks_like_kit(title):
                        continue

                    aro_found = detect_aro(title)
                    if aro_found not in (13, 14, 15):
                        continue

                    _push_topn(top_by_aro[aro_found], {
                        "source": d.get("source", src),
                        "title": title[:160],
                        "url": url,
                        "price_cents": price,
                        "aro": aro_found,
                    }, n=10)

                    if price <= LIMITS[aro_found]:
                        if upsert_deal(conn, d):
                            dd = dict(d)
                            dd["title"] = f"{title[:180]} (aro {aro_found})"
                            new_items.append(dd)

                polite_sleep()

    if new_items:
        lines = [f"Promoções dentro do limite: {len(new_items)}"]
        for d in new_items[:20]:
            lines.append(f"- [{d['source']}] {d['title']} | {format_price(d['price_cents'])}\n  {d['url']}")
        if len(new_items) > 20:
            lines.append(f"(+{len(new_items)-20} itens)")
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
        return

    # relatório (agora deve vir com itens)
    lines = [
        "TireBot: sem resultados dentro dos limites.",
        f"Itens lidos: {total_candidates} (PneuStore={stats['PneuStore']}, PneuFree={stats['PneuFree']}, Magalu={stats['MagazineLuiza']}).",
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
