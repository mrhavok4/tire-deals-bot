import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TireBot/1.0)"
}

def price_to_cents(text: str) -> Optional[int]:
    if not text:
        return None
    # captura "1.234,56"
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})", text)
    if not m:
        return None
    whole = m.group(1).replace(".", "")
    cents = m.group(2)
    return int(whole) * 100 + int(cents)

def normalize_text(el) -> str:
    return el.get_text(" ", strip=True) if el else ""

def find_price_near(node) -> Optional[int]:
    cur = node
    for _ in range(5):
        if cur is None:
            break
        txt = cur.get_text(" ", strip=True)
        if "R$" in txt or re.search(r"\d+,\d{2}", txt):
            val = price_to_cents(txt)
            if val is not None:
                return val
        cur = cur.parent
    return None

# ---------- ATACADÃO ----------
def scrape_atacadao(url: str) -> List[Dict[str, Any]]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    deals: List[Dict[str, Any]] = []

    # tenta capturar links de produtos
    anchors = soup.select("a[href]")
    for a in anchors:
        href = a.get("href", "").strip()
        title = a.get_text(" ", strip=True)

        if not href or not title:
            continue
        if "pneu" not in title.lower():
            continue

        full_url = urljoin(url, href)

        # preço (heurística por proximidade)
        price = find_price_near(a)

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price,
            "source": "Atacadão",
        })

        if len(deals) >= 60:
            break

    return deals

# ---------- DPASCHOAL ----------
def scrape_dpaschoal(url: str) -> List[Dict[str, Any]]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    deals: List[Dict[str, Any]] = []

    anchors = soup.select("a[href]")
    for a in anchors:
        href = a.get("href", "").strip()
        title = a.get_text(" ", strip=True)

        if not href or not title:
            continue
        if "pneu" not in title.lower():
            continue

        full_url = urljoin(url, href)

        price = find_price_near(a)

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price,
            "source": "DPaschoal",
        })

        if len(deals) >= 60:
            break

    return deals
