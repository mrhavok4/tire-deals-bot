import re
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

def _price_to_cents(text: str) -> Optional[int]:
    if not text:
        return None
    text = text.strip()

    m = re.search(r"(\d{1,3}(\.\d{3})*|\d+),(\d{2})", text)
    if m:
        whole = m.group(1).replace(".", "")
        cents = m.group(3)
        return int(whole) * 100 + int(cents)

    m = re.search(r"(\d{1,3}(\.\d{3})*|\d+)", text)
    if m:
        whole = m.group(1).replace(".", "")
        return int(whole) * 100
    return None

def scrape_generic_listing(url: str, source: str) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TireBot/1.0)"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    deals: List[Dict[str, Any]] = []
    for a in soup.select("a[href]")[:600]:
        title = a.get_text(" ", strip=True)
        href = a["href"].strip()

        if not title or len(title) < 8:
            continue
        if "pneu" not in title.lower():
            continue

        full_url = urljoin(url, href)

        # tenta achar preço próximo
        container = a.parent
        price_text = ""
        for _ in range(3):
            if not container:
                break
            txt = container.get_text(" ", strip=True)
            if "R$" in txt or re.search(r"\d+,\d{2}", txt):
                price_text = txt
                break
            container = container.parent

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": _price_to_cents(price_text),
            "source": source,
        })

        if len(deals) >= 40:
            break

    return deals
