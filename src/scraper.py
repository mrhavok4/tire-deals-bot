import re
import time
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, quote_plus

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.6,en;q=0.5",
    "Connection": "keep-alive",
}
TIMEOUT = 30

UNAVAILABLE_WORDS = ["indisponível", "indisponivel", "esgotado", "sem estoque", "fora de estoque"]

def polite_sleep():
    time.sleep(1.0)

def _has_unavailable(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in UNAVAILABLE_WORDS)

def _price_to_cents(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d{1,3}(?:\.\d{3})*),(\d{2})", text)
    if not m:
        return None
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(2))

def _best_price_from_text(txt: str) -> Optional[int]:
    prices = re.findall(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", txt)
    cents = []
    for p in prices:
        c = _price_to_cents(p)
        if c is not None:
            cents.append(c)
    return max(cents) if cents else None

def _get(url: str) -> Tuple[Optional[str], int]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code in (403, 429):
        print(f"[WARN] blocked {r.status_code} -> {url}")
        return None, r.status_code
    if r.status_code >= 400:
        print(f"[WARN] http {r.status_code} -> {url}")
        return None, r.status_code
    return r.text, r.status_code

def parse_measure(measure: str) -> Optional[Dict[str, int]]:
    m = re.search(r"(\d{3})\s*/\s*(\d{2})\s*R\s*(\d{2})", (measure or "").upper())
    if not m:
        return None
    return {"largura": int(m.group(1)), "altura": int(m.group(2)), "aro": int(m.group(3))}

def measure_to_slug(measure: str) -> Optional[str]:
    pm = parse_measure(measure)
    if not pm:
        return None
    return f"{pm['largura']}-{pm['altura']}-r{pm['aro']}"

def _extract_deals_from_page(base_url: str, html: str, source: str, product_href_hint: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    # pega links de produto e busca preço no “card” (subindo alguns pais)
    for a in soup.select(f"a[href*='{product_href_hint}']"):
        href = (a.get("href") or "").strip()
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        if "pneu" not in title.lower():
            continue

        full_url = href if href.startswith("http") else urljoin(base_url, href)

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

            # preferir “no pix” / “à vista” quando aparecer
            m_pix = re.search(r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}).{0,25}\bPix\b", text_blob, flags=re.I)
            if m_pix:
                price_cents = _price_to_cents(m_pix.group(1))
                break

            m_av = re.search(r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}).{0,25}\bà\s*vista\b", text_blob, flags=re.I)
            if m_av:
                price_cents = _price_to_cents(m_av.group(1))
                break

            best = _best_price_from_text(text_blob)
            if best is not None:
                price_cents = best
                break

            container = container.parent

        if price_cents is None:
            continue
        if price_cents < 10000:  # anti-ruído
            continue

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price_cents,
            "source": source,
        })

        if len(deals) >= 60:
            break

    return deals

# -------- PneuStore --------
def scrape_pneustore(measure: str) -> List[Dict[str, Any]]:
    slug = measure_to_slug(measure)
    if not slug:
        return []
    url = f"https://www.pneustore.com.br/categorias/pneus-de-carro/{slug}"
    html, _ = _get(url)
    if not html:
        return []
    # PneuStore costuma usar /produto/ nas URLs
    return _extract_deals_from_page(url, html, "PneuStore", "/produto/")

# -------- PneuFree --------
def scrape_pneufree(measure: str) -> List[Dict[str, Any]]:
    pm = parse_measure(measure)
    if not pm:
        return []
    url = f"https://www.pneufree.com.br/pesquisa?altura={pm['altura']}&aro={pm['aro']}&largura={pm['largura']}"
    html, _ = _get(url)
    if not html:
        return []
    # PneuFree tem URLs variadas; usar heurística “pneu” + preço no card. Hint mais amplo:
    return _extract_deals_from_page(url, html, "PneuFree", "/pneu")

# -------- Magalu --------
def build_magalu_url(query: str) -> str:
    # Magalu usa %2B no path como separador
    enc = quote_plus(query)        # espaço vira '+'
    enc = enc.replace("+", "%2B")  # no path vira %2B
    return f"https://www.magazineluiza.com.br/busca/{enc}/"

def scrape_magalu(query: str) -> List[Dict[str, Any]]:
    url = build_magalu_url(query)
    html, _ = _get(url)
    if not html:
        return []
    # Magalu produto normalmente contém "/p/"
    return _extract_deals_from_page(url, html, "MagazineLuiza", "/p/")
