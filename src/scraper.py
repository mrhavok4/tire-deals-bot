import re
import time
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, quote_plus

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TireBot/1.0)"}
TIMEOUT = 30

UNAVAILABLE_WORDS = ["indisponível", "indisponivel", "esgotado", "sem estoque", "fora de estoque"]

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

def polite_sleep():
    time.sleep(1.0)

def _get(url: str) -> Optional[str]:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code in (403, 429):
        return None
    r.raise_for_status()
    return r.text

# ---------------- helpers de medida ----------------
def parse_measure(measure: str) -> Optional[Dict[str, int]]:
    # ex: "175/70 R13"
    m = re.search(r"(\d{3})\s*/\s*(\d{2})\s*R\s*(\d{2})", measure.upper())
    if not m:
        return None
    return {"largura": int(m.group(1)), "altura": int(m.group(2)), "aro": int(m.group(3))}

def measure_to_slug(measure: str) -> Optional[str]:
    pm = parse_measure(measure)
    if not pm:
        return None
    return f"{pm['largura']}-{pm['altura']}-r{pm['aro']}"

# ---------------- PNEUSTORE (por slug de medida) ----------------
def scrape_pneustore(measure: str) -> List[Dict[str, Any]]:
    slug = measure_to_slug(measure)
    if not slug:
        return []
    url = f"https://www.pneustore.com.br/categorias/pneus-de-carro/{slug}"

    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    # pegar cards pelo padrão "à vista" + link do produto na mesma área
    for block in soup.select("a[href]"):
        title = block.get_text(" ", strip=True)
        href = (block.get("href") or "").strip()
        if not title or not href:
            continue
        if "pneu" not in title.lower():
            continue

        # sobe no container para achar preços "à vista"
        container = block
        price_cents = None
        text_blob = ""
        for _ in range(8):
            if container is None:
                break
            text_blob = container.get_text(" ", strip=True)
            if "à vista" in text_blob.lower():
                # preferir preço "à vista"
                # exemplo no HTML: "R$ 259,90  à vista"
                m = re.search(r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2})\s*à\s*vista", text_blob, flags=re.I)
                if m:
                    price_cents = _price_to_cents(m.group(1))
                    break
            container = container.parent

        if price_cents is None:
            continue
        if price_cents < 10000:  # anti-ruído
            continue
        if _has_unavailable(text_blob):
            continue

        full_url = href if href.startswith("http") else urljoin(url, href)

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price_cents,
            "source": "PneuStore",
        })
        if len(deals) >= 40:
            break

    return deals

# ---------------- PNEUFREE (por params) ----------------
def scrape_pneufree(measure: str) -> List[Dict[str, Any]]:
    pm = parse_measure(measure)
    if not pm:
        return []
    url = f"https://www.pneufree.com.br/pesquisa?largura={pm['largura']}&altura={pm['altura']}&aro={pm['aro']}"

    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    # fallback genérico: procurar links com "pneu" e um preço no mesmo card
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        href = (a.get("href") or "").strip()
        if not title or not href:
            continue
        if "pneu" not in title.lower():
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
            best = _best_price_from_text(text_blob)
            if best is not None:
                price_cents = best
                break
            container = container.parent

        if price_cents is None or price_cents < 10000:
            continue

        full_url = href if href.startswith("http") else urljoin(url, href)

        deals.append({
            "url": full_url,
            "title": title[:180],
            "price_cents": price_cents,
            "source": "PneuFree",
        })
        if len(deals) >= 40:
            break

    return deals

# ---------------- MAGALU (encoding correto no path) ----------------
def build_magalu_url(query: str) -> str:
    # Magalu usa %2B no path (equivalente a "+")
    enc = quote_plus(query)              # espaços -> "+", "/" -> "%2F"
    enc = enc.replace("+", "%2B")        # "+" literal no path
    return f"https://www.magazineluiza.com.br/busca/{enc}/"

def scrape_magalu(query: str) -> List[Dict[str, Any]]:
    url = build_magalu_url(query)
    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    # A página tem itens em lista; usar links numerados e texto com preço
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        href = (a.get("href") or "").strip()
        if not title or not href:
            continue
        if "pneu" not in title.lower():
            continue

        full_url = href if href.startswith("http") else urljoin(url, href)

        # evitar links que não parecem produto
        if "/p/" not in full_url:
            continue

        container = a
        price_cents = None
        text_blob = ""
        for _ in range(10):
            if container is None:
                break
            text_blob = container.get_text(" ", strip=True)
            if _has_unavailable(text_blob):
                price_cents = None
                break

            # preferir pix
            m = re.search(r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2})\s+no\s+Pix", text_blob, flags=re.I)
            if m:
                price_cents = _price_to_cents(m.group(1))
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
            "source": "MagazineLuiza",
        })

        if len(deals) >= 40:
            break

    return deals
