import re
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TireDealsBot/1.0)"}
TIMEOUT = 30

def _price_to_cents_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})*),(\d{2})", text)
    if m:
        whole = int(m.group(1).replace(".", ""))
        cents = int(m.group(2))
        return whole * 100 + cents
    m = re.search(r"\b(\d{1,3}(?:\.\d{3})*)\b", text)
    if m:
        whole = int(m.group(1).replace(".", ""))
        return whole * 100
    return None

def _get(url: str) -> Optional[str]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code in (403, 429):
        return None
    r.raise_for_status()
    return r.text

# ---------------- Mercado Livre ----------------
def build_ml_search_url(query: str) -> str:
    q = query.strip().replace(" ", "-")
    return f"https://lista.mercadolivre.com.br/{q}"

def scrape_mercadolivre(search_url: str) -> List[Dict[str, Any]]:
    html = _get(search_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    for item in soup.select("li.ui-search-layout__item"):
        a = item.select_one("a.ui-search-link")
        title_el = item.select_one("h2.ui-search-item__title")
        if not a or not title_el:
            continue

        url = a.get("href", "").strip()
        title = title_el.get_text(" ", strip=True)

        frac = item.select_one("span.price-tag-fraction")
        cents = item.select_one("span.price-tag-cents")
        price_cents = None

        if frac:
            frac_txt = frac.get_text(strip=True).replace(".", "")
            cen_txt = cents.get_text(strip=True) if cents else "00"
            if frac_txt.isdigit() and cen_txt.isdigit():
                price_cents = int(frac_txt) * 100 + int(cen_txt)

        if price_cents is None:
            price_cents = _price_to_cents_from_text(item.get_text(" ", strip=True))

        deals.append({
            "url": url,
            "title": title[:180],
            "price_cents": price_cents,
            "source": "MercadoLivre",
        })

        if len(deals) >= 40:
            break

    return deals

# ---------------- Casas Bahia ----------------
def build_casasbahia_search_url(query: str) -> str:
    q = query.strip().replace(" ", "%20")
    return f"https://www.casasbahia.com.br/busca/{q}"

def scrape_casasbahia(search_url: str) -> List[Dict[str, Any]]:
    html = _get(search_url)
    if not html:
        return []  # se 403/429, apenas ignora

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        title = a.get_text(" ", strip=True)

        if not href or not title or "pneu" not in title.lower():
            continue

        full_url = urljoin(search_url, href)

        container = a
        price_cents = None
        for _ in range(6):
            if container is None:
                break
            txt = container.get_text(" ", strip=True)
            m = re.search(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", txt)
            if m:
                price_cents = _price_to_cents_from_text(m.group(0))
                break
            container = container.parent

        if price_cents is None:
            continue

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price_cents,
            "source": "CasasBahia",
        })

        if len(deals) >= 40:
            break

    return deals

# ---------------- Magazine Luiza ----------------
def build_magalu_search_url(query: str) -> str:
    q = query.strip().replace(" ", "-")
    return f"https://www.magazineluiza.com.br/busca/{q}/"

def scrape_magalu(search_url: str) -> List[Dict[str, Any]]:
    html = _get(search_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        title = a.get_text(" ", strip=True)

        if not href or not title or "pneu" not in title.lower():
            continue

        full_url = urljoin(search_url, href)

        container = a
        price_cents = None
        for _ in range(7):
            if container is None:
                break
            txt = container.get_text(" ", strip=True)
            m = re.search(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", txt)
            if m:
                price_cents = _price_to_cents_from_text(m.group(0))
                break
            container = container.parent

        if price_cents is None:
            continue

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price_cents,
            "source": "MagazineLuiza",
        })

        if len(deals) >= 40:
            break

    return deals

def polite_sleep():
    time.sleep(1.2)
