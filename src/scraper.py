import re
import time
import random
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

def polite_sleep():
    time.sleep(random.uniform(0.5, 1.2))

# ---------- helpers ----------
def parse_measure(measure: str) -> Optional[Dict[str, str]]:
    """
    "175/70 R13" -> {"largura":"175","altura":"70","aro":"13"}
    """
    if not measure:
        return None
    m = re.search(r"(\d{3})\s*/\s*(\d{2})\s*R\s*(\d{2})", measure.upper())
    if not m:
        return None
    return {"largura": m.group(1), "altura": m.group(2), "aro": m.group(3)}

def _get(url: str) -> Optional[str]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code in (403, 429):
        return None
    r.raise_for_status()
    return r.text

def _brl_to_cents_from_any(text: str) -> Optional[int]:
    if not text:
        return None
    # pega todos "R$ x.xxx,yy" e devolve o maior (evita parcela)
    prices = re.findall(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", text)
    cents = []
    for p in prices:
        m = re.search(r"R\$\s*([\d\.\,]+)", p)
        if not m:
            continue
        num = m.group(1).replace(".", "").replace(",", ".")
        try:
            cents.append(int(round(float(num) * 100)))
        except:
            pass
    return max(cents) if cents else None

def _looks_unavailable(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ["indisponível", "indisponivel", "esgotado", "sem estoque", "fora de estoque"])

def _looks_like_kit(title: str) -> bool:
    t = (title or "").lower()
    return any(w in t for w in ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"])

# ---------- PneuStore ----------
def _pneustore_url_for_measure(measure: str) -> str:
    pm = parse_measure(measure)
    if pm:
        # Padrão comum: /categorias/pneus-de-carro/175-70-r13
        slug = f"{pm['largura']}-{pm['altura']}-r{pm['aro']}".lower()
        return f"https://www.pneustore.com.br/categorias/pneus-de-carro/{slug}"
    # fallback genérico
    return f"https://www.pneustore.com.br/busca?q={quote_plus(measure)}"

def scrape_pneustore(measure: str) -> List[Dict[str, Any]]:
    url = _pneustore_url_for_measure(measure)
    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    # Estratégia robusta:
    # - procura anchors que parecem produto e extrai texto do card
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        if "pneu" not in title.lower():
            continue
        if _looks_like_kit(title):
            continue

        href = a.get("href") or ""
        full_url = urljoin(url, href)

        # evita links óbvios que não são produto
        if "/categorias/" in full_url or "/busca" in full_url:
            continue

        card = a
        card_text = ""
        for _ in range(6):
            if card is None:
                break
            card_text = card.get_text(" ", strip=True)
            if "R$" in card_text:
                break
            card = card.parent

        if _looks_unavailable(card_text):
            continue

        price_cents = _brl_to_cents_from_any(card_text)
        if price_cents is None:
            continue

        # anti-ruído
        if price_cents < 10000:
            continue

        deals.append({
            "source": "PneuStore",
            "title": title[:180],
            "url": full_url,
            "price_cents": price_cents,
        })

    # dedup por url
    seen = set()
    out = []
    for d in deals:
        if d["url"] in seen:
            continue
        seen.add(d["url"])
        out.append(d)

    return out[:60]

# ---------- PneuFree ----------
def _pneufree_url_for_measure(measure: str) -> str:
    pm = parse_measure(measure)
    if pm:
        # tentativa por parâmetros (caso exista)
        return f"https://www.pneufree.com.br/busca?busca={quote_plus(measure)}"
    return f"https://www.pneufree.com.br/busca?busca={quote_plus(measure)}"

def _scrape_pneufree_html(measure: str) -> List[Dict[str, Any]]:
    url = _pneufree_url_for_measure(measure)
    html = _get(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")

    # Se o HTML vier "vazio" (JS), costuma ter poucos/nenhum "R$"
    if soup.get_text(" ", strip=True).count("R$") < 2:
        return []

    deals: List[Dict[str, Any]] = []
    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        if not title or "pneu" not in title.lower():
            continue
        if _looks_like_kit(title):
            continue

        href = a.get("href") or ""
        full_url = urljoin(url, href)

        card = a
        card_text = ""
        for _ in range(7):
            if card is None:
                break
            card_text = card.get_text(" ", strip=True)
            if "R$" in card_text:
                break
            card = card.parent

        if _looks_unavailable(card_text):
            continue

        price_cents = _brl_to_cents_from_any(card_text)
        if price_cents is None or price_cents < 10000:
            continue

        deals.append({
            "source": "PneuFree",
            "title": title[:180],
            "url": full_url,
            "price_cents": price_cents,
        })

    # dedup
    seen = set()
    out = []
    for d in deals:
        if d["url"] in seen:
            continue
        seen.add(d["url"])
        out.append(d)

    return out[:60]

def _scrape_pneufree_playwright(measure: str) -> List[Dict[str, Any]]:
    url = _pneufree_url_for_measure(measure)
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, locale="pt-BR")
        page.goto(url, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    for a in soup.select("a[href]"):
        title = a.get_text(" ", strip=True)
        if not title or "pneu" not in title.lower():
            continue
        if _looks_like_kit(title):
            continue

        href = a.get("href") or ""
        full_url = urljoin(url, href)

        card = a
        card_text = ""
        for _ in range(8):
            if card is None:
                break
            card_text = card.get_text(" ", strip=True)
            if "R$" in card_text:
                break
            card = card.parent

        if _looks_unavailable(card_text):
            continue

        price_cents = _brl_to_cents_from_any(card_text)
        if price_cents is None or price_cents < 10000:
            continue

        deals.append({
            "source": "PneuFree",
            "title": title[:180],
            "url": full_url,
            "price_cents": price_cents,
        })

    # dedup
    seen = set()
    out = []
    for d in deals:
        if d["url"] in seen:
            continue
        seen.add(d["url"])
        out.append(d)

    return out[:60]

def scrape_pneufree(measure: str) -> List[Dict[str, Any]]:
    deals = _scrape_pneufree_html(measure)
    if deals:
        return deals
    # fallback JS
    return _scrape_pneufree_playwright(measure)

# ---------- Magalu (o seu estava funcionando) ----------
def scrape_magalu(query: str) -> List[Dict[str, Any]]:
    url = f"https://www.magazineluiza.com.br/busca/{quote_plus(query).replace('%2F','%20')}/"
    html = _get(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    deals: List[Dict[str, Any]] = []

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        title = a.get_text(" ", strip=True)
        if not title or "pneu" not in title.lower():
            continue
        if _looks_like_kit(title):
            continue

        full_url = urljoin(url, href)
        if "/busca/" in full_url:
            continue
        if "/p/" not in full_url:
            continue

        card = a
        card_text = ""
        price_cents = None
        for _ in range(10):
            if card is None:
                break
            card_text = card.get_text(" ", strip=True)

            if _looks_unavailable(card_text):
                price_cents = None
                break

            # Preferir "no Pix"
            m_pix = re.search(r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2})\s+no\s+Pix", card_text, flags=re.I)
            if m_pix:
                price_cents = _brl_to_cents_from_any(m_pix.group(1))
                break

            if "R$" in card_text:
                price_cents = _brl_to_cents_from_any(card_text)
                break

            card = card.parent

        if price_cents is None or price_cents < 10000:
            continue

        deals.append({
            "source": "MagazineLuiza",
            "title": title[:180],
            "url": full_url,
            "price_cents": price_cents,
        })

    # dedup
    seen = set()
    out = []
    for d in deals:
        if d["url"] in seen:
            continue
        seen.add(d["url"])
        out.append(d)

    return out[:60]
