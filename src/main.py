import os
import re
from typing import Optional, Dict, Any, List, DefaultDict
from collections import defaultdict

from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.jina import (
    jina_search, jina_read, normalize_url, best_price_cents,
    contains_unavailable, polite_sleep
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

DB_PATH = "tirebot.sqlite"

# Limites por aro (centavos)
LIMITS = {13: 20000, 14: 26000, 15: 29000}

MEASURES = {
    13: ["175/70 R13", "165/70 R13", "165/80 R13"],
    14: ["175/65 R14", "185/60 R14", "165/70 R14"],
    15: ["185/65 R15", "195/55 R15", "195/65 R15", "185/60 R15"],
}

UNWANTED = ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"]

SITES = [
    "magazineluiza.com.br",
    "pneustore.com.br",
    "pneufree.com.br",
    "casasbahia.com.br",
    "extra.com.br",
]

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
    del topn[n:]

def run():
    conn = connect(DB_PATH)

    new_items: List[Dict[str, Any]] = []
    top_by_aro = {13: [], 14: [], 15: []}

    stats: DefaultDict[str, int] = defaultdict(int)
    total_urls = 0
    total_pages = 0

    for aro, measures in MEASURES.items():
        for measure in measures:
            query = f"promoção pneu {measure} preço"

            try:
                urls = jina_search(query, sites=SITES, max_urls=8)
            except Exception as e:
                print(f"[WARN] jina_search error: {e}")
                urls = []

            total_urls += len(urls)

            for u in urls:
                src = None
                host = ""
                try:
                    host = re.sub(r"^www\.", "", (re.search(r"https?://([^/]+)/", u) or ["",""])[1])
                except Exception:
                    host = ""

                if "magazineluiza" in host: src = "MagazineLuiza"
                elif "pneustore" in host: src = "PneuStore"
                elif "pneufree" in host: src = "PneuFree"
                elif "casasbahia" in host: src = "CasasBahia"
                elif "extra" in host: src = "Extra"
                else: src = host or "Web"

                try:
                    page_txt = jina_read(u)
                except Exception as e:
                    print(f"[WARN] jina_read error {src}: {e}")
                    continue

                total_pages += 1

                if contains_unavailable(page_txt):
                    continue

                price = best_price_cents(page_txt)
                if price is None:
                    continue

                # anti-ruído: pneus não costumam < R$100
                if price < 10000:
                    continue

                # título: tenta puxar algo do início do texto; fallback no measure
                title = measure
                # tenta pegar a primeira linha "limpa"
                first_line = (page_txt.strip().splitlines()[0] if page_txt else "").strip()
                if first_line and len(first_line) <= 140:
                    title = first_line

                if looks_like_kit(title):
                    continue

                # detecta aro no título ou no conteúdo
                aro_found = detect_aro(title) or detect_aro(page_txt)
                if aro_found not in (13, 14, 15):
                    continue

                deal = {
                    "source": src,
                    "title": title[:180],
                    "url": normalize_url(u),
                    "price_cents": price,
                }

                stats[src] += 1

                # TOP mais baratos sempre
                _push_topn(top_by_aro[aro_found], {
                    "source": deal["source"],
                    "title": deal["title"][:160],
                    "url": deal["url"],
                    "price_cents": deal["price_cents"],
                }, n=10)

                # dentro do limite -> alerta e grava
                if price <= LIMITS[aro_found]:
                    if upsert_deal(conn, deal):
                        dd = dict(deal)
                        dd["title"] = f"{dd['title']} (aro {aro_found})"
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

    # relatório
    lines = [
        "TireBot: sem resultados dentro dos limites.",
        f"URLs encontradas: {total_urls}. Páginas lidas: {total_pages}.",
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
