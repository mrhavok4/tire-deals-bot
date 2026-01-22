import re
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TireDealsBot/1.0)"}
TIMEOUT = 30

UNAVAILABLE_WORDS = [
    "indisponível", "indisponivel", "esgotado", "sem estoque", "fora de estoque"
]

def _has_unavailable(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in UNAVAILABLE_WORDS)

def _price_to_cents_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})*),(\d{2})", text)
    if m:
        whole = int(m.group(1).replace(".", ""))
        cents = int(m.group(2))
        return whole * 100 + cents
    return None

def _get(url: str) -> Optional[str]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code in (403, 429):
        return None
    r.raise_for_status()
    return r.text

def _best_price_from_text(txt: str) -> Optional[int]:
    prices = re.findall(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", txt)
    cents_list = []
    for p in prices:
        c = _price_to_cents_from_text(p)
        if c is not None:
            cents_list.append(c)
    return max(cents_list) if cents_list else None

def polite_sleep():
    time.sleep(1.2)

# ---------------- Mercado Livre ----------------
def build_ml_search_url(query: str) -> str:
    q = query.strip().replace(" ", "-")
    return f"https://lista.mercadolivre.com.br/{q}"

def _is_ml_item_url(u: str) -> bool:
    # Aceita links típicos de item do ML (muito mais permissivo)
    try:
        p = urlparse(u)
    except Exception:
        return False
    if not p.scheme.startswith("http"):
        return False
    host = (p.netloc or "").lower()
    if "mercadolivre.com" not in host:
        return False
    # Evita links de navegação óbvios
    if "/_from/" in (p.path or ""):
        return False
    # Links de item costumam ter "/MLB-" ou terminar com id; mas não vamos travar demais.
    return True

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

        url = (a.get("href") or "").strip()
        title = title_el.get_text(" ", strip=True)
        blob_txt = item.get_text(" ", strip=True)

        if not url or not title:
            continue
        if not _is_ml_item_url(url):
            continue
        if _has_unavailable(blob_txt):
            continue

        frac = item.select_one("span.price-tag-fraction")
        cents = item.select_one("span.price-tag-cents")
        price_cents = None

        if frac:
            frac_txt = frac.get_text(strip=True).replace(".", "")
            cen_txt = cents.get_text(strip=True) if cents else "00"
            if frac_txt.isdigit() and cen_txt.isdigit():
                price_cents = int(frac_txt) * 100 + int(cen_txt)

        if price_cents is None:
            price_cents = _best_price_from_text(blob_txt)

        if price_cents is None or price_cents < 10000:
            continue

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
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        if "pneu" not in title.lower():
            continue

        full_url = urljoin(search_url, href)
        if "/busca/" in full_url:
            continue

        container = a
        price_cents = None
        text_blob = ""
        for _ in range(8):
            if container is None:
                break
            text_blob = container.get_text(" ", strip=True)
            if _has_unavailable(text_blob):
                price_cents = None
                break

            pix_match = re.search(
                r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2})\s+no\s+pix",
                text_blob,
                flags=re.I,
            )
            if pix_match:
                price_cents = _price_to_cents_from_text(pix_match.group(1))
                break

            best = _best_price_from_text(text_blob)
            if best is not None:
                price_cents = best
                break

            container = container.parent

        if price_cents is None or price_cents < 10000:
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
        href = (a.get("href") or "").strip()
        title = a.get_text(" ", strip=True)

        if not href or not title:
            continue
        if "pneu" not in title.lower():
            continue

        full_url = urljoin(search_url, href)

        if "/busca/" in full_url:
            continue
        if "/p/" not in full_url:
            continue

        container = a
        price_cents = None
        for _ in range(10):
            if container is None:
                break
            txt = container.get_text(" ", strip=True)

            if _has_unavailable(txt):
                price_cents = None
                break

            pix_match = re.search(
                r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2})\s+no\s+Pix",
                txt,
                flags=re.I,
            )
            if pix_match:
                price_cents = _price_to_cents_from_text(pix_match.group(1))
                break

            best = _best_price_from_text(txt)
            if best is not None:
                price_cents = best
                break

            container = container.parent

        if price_cents is None or price_cents < 10000:
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
