import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TireBot/1.0)"
}

def price_to_cents(text: str):
    if not text:
        return None
    m = re.search(r"(\d{1,3}(\.\d{3})*|\d+),(\d{2})", text)
    if not m:
        return None
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(3))

# ---------- ATACADÃO ----------
def scrape_atacadao(url: str) -> List[Dict[str, Any]]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    deals = []
    for card in soup.select("a[href*='/produto/']"):
        title = card.get_text(" ", strip=True)
        if "pneu" not in title.lower():
            continue

        full_url = urljoin(url, card["href"])
        container = card.find_parent("article") or card.parent
        price_el = container.select_one("[class*='price'], [class*='Price']")
        price = price_to_cents(price_el.get_text(strip=True) if price_el else "")

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price,
            "source": "Atacadão",
        })

        if len(deals) >= 40:
            break

    return deals

# ---------- DPASCHOAL ----------
def scrape_dpaschoal(url: str) -> List[Dict[str, Any]]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    deals = []
    for card in soup.select("a[href*='/pneu']"):
        title = card.get_text(" ", strip=True)
        if "pneu" not in title.lower():
            continue

        full_url = urljoin(url, card["href"])
        container = card.find_parent("div")
        price_el = container.select_one("[class*='price'], [class*='valor']")
        price = price_to_cents(price_el.get_text(strip=True) if price_el else "")

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price,
            "source": "DPaschoal",
        })

        if len(deals) >= 40:
            break

    return deals
