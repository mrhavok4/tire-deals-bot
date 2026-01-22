import re
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TireBot/1.0)"}
TIMEOUT = 30

def price_to_cents(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})*),(\d{2})", text)
    if not m:
        return None
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(2))

def polite_sleep():
    time.sleep(1.2)

# ---------------- PNEUSTORE ----------------
def scrape_pneustore(query: str) -> List[Dict[str, Any]]:
    url = f"https://www.pneustore.com.br/busca?q={query.replace(' ', '%20')}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    deals = []
    for card in soup.select("div.product-item"):
        title_el = card.select_one(".product-item-link")
        price_el = card.select_one(".price")

        if not title_el or not price_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href")
        price = price_to_cents(price_el.get_text(strip=True))

        if price is None:
            continue

        deals.append({
            "url": urljoin(url, href),
            "title": title[:180],
            "price_cents": price,
            "source": "PneuStore",
        })

        if len(deals) >= 40:
            break

    return deals

# ---------------- PNEUFREE ----------------
def scrape_pneufree(query: str) -> List[Dict[str, Any]]:
    url = f"https://www.pneufree.com.br/busca?q={query.replace(' ', '%20')}"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    deals = []
    for card in soup.select("div.product"):
        title_el = card.select_one("a.product-title")
        price_el = card.select_one("span.price")

        if not title_el or not price_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href")
        price = price_to_cents(price_el.get_text(strip=True))

        if price is None:
            continue

        deals.append({
            "url": urljoin(url, href),
            "title": title[:180],
            "price_cents": price,
            "source": "PneuFree",
        })

        if len(deals) >= 40:
            break

    return deals

# ---------------- MAGAZINE LUIZA ----------------
def scrape_magalu(query: str) -> List[Dict[str, Any]]:
    url = f"https://www.magazineluiza.com.br/busca/{query.replace(' ', '-')}/"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    deals = []
    for a in soup.select("a[href*='/p/']"):
        title = a.get_text(" ", strip=True)
        if "pneu" not in title.lower():
            continue

        container = a.parent
        price = None
        for _ in range(8):
            if not container:
                break
            txt = container.get_text(" ", strip=True)
            m = re.search(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", txt)
            if m:
                price = price_to_cents(m.group(0))
                break
            container = container.parent

        if price is None or price < 10000:
            continue

        deals.append({
            "url": urljoin(url, a.get("href")),
            "title": title[:180],
            "price_cents": price,
            "source": "MagazineLuiza",
        })

        if len(deals) >= 40:
            break

    return deals
