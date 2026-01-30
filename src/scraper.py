import re
import json
import time
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"

UNAVAILABLE_WORDS = ["indisponível", "indisponivel", "esgotado", "sem estoque", "fora de estoque"]

def polite_sleep():
    time.sleep(1.0)

def normalize_url(u: str) -> str:
    p = urlparse(u)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))

def parse_measure(measure: str) -> Optional[Dict[str, str]]:
    m = re.search(r"(\d{3})\s*/\s*(\d{2})\s*R\s*(\d{2})", (measure or "").upper())
    if not m:
        return None
    return {"largura": m.group(1), "altura": m.group(2), "aro": m.group(3)}

def detect_aro(text: str) -> Optional[int]:
    m = re.search(r"\bR\s*(13|14|15)\b", (text or "").upper())
    return int(m.group(1)) if m else None

def looks_unavailable(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in UNAVAILABLE_WORDS)

def looks_like_kit(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"])

def brl_to_cents_from_any(text: str) -> Optional[int]:
    # pega todos os R$ x.xxx,yy e usa o MAIOR (evita pegar valor de parcela)
    prices = re.findall(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", text or "")
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

# ---------------- Mercado Livre ----------------
def scrape_mercadolivre(query: str) -> List[Dict[str, Any]]:
    url = f"https://lista.mercadolivre.com.br/{quote_plus(query).replace('%20','-')}"
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}, timeout=30)
    if r.status_code in (403, 429):
        return []
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    deals: List[Dict[str, Any]] = []

    for item in soup.select("li.ui-search-layout__item"):
        a = item.select_one("a.ui-search-link")
        title_el = item.select_one("h2.ui-search-item__title")
        if not a or not title_el:
            continue

        href = (a.get("href") or "").strip()
        title = title_el.get_text(" ", strip=True)
        blob = item.get_text(" ", strip=True)

        if not href or not title:
            continue
        if looks_unavailable(blob) or looks_like_kit(title):
            continue

        # preço no card
        frac = item.select_one("span.price-tag-fraction")
        cents = item.select_one("span.price-tag-cents")
        price_cents = None
        if frac:
            ft = frac.get_text(strip=True).replace(".", "")
            ct = (cents.get_text(strip=True) if cents else "00")
            if ft.isdigit() and ct.isdigit():
                price_cents = int(ft) * 100 + int(ct)
        if price_cents is None:
            price_cents = brl_to_cents_from_any(blob)

        if price_cents is None or price_cents < 10000:
            continue

        deals.append({
            "source": "MercadoLivre",
            "title": title[:180],
            "url": normalize_url(href),
            "price_cents": price_cents,
        })

        if len(deals) >= 50:
            break

    return deals

# ---------------- Shopee ----------------
def scrape_shopee(query: str) -> List[Dict[str, Any]]:
    # Shopee geralmente expõe dados no __NEXT_DATA__ (JSON) na página de busca
    url = f"https://shopee.com.br/search?keyword={quote_plus(query)}"
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=30,
    )
    if r.status_code in (403, 429):
        return []
    r.raise_for_status()

    html = r.text
    if looks_unavailable(html):
        return []

    # extrai __NEXT_DATA__
    m = re.search(r'__NEXT_DATA__\s*=\s*({.*?})\s*</script>', html, flags=re.S)
    if not m:
        return []

    try:
        data = json.loads(m.group(1))
    except Exception:
        return []

    # navegar de forma defensiva (estrutura pode mudar)
    # normalmente itens ficam em props.pageProps.initialState.search.items / ou algo similar
    items = []
    try:
        # tentativa 1
        items = data["props"]["pageProps"]["initialState"]["search"]["items"]
    except Exception:
        pass
    if not items:
        try:
            # tentativa 2 (fallback amplo)
            blob = json.dumps(data)
            # não dá pra reconstruir sem estrutura -> aborta
            return []
        except Exception:
            return []

    deals: List[Dict[str, Any]] = []

    for it in items:
        title = (it.get("name") or "").strip()
        if not title or "pneu" not in title.lower():
            continue
        if looks_like_kit(title):
            continue

        # preço (Shopee às vezes dá em centavos/inteiro)
        # campos comuns: price, price_min, price_max (em 100000? depende)
        price_raw = it.get("price_min") or it.get("price") or it.get("price_max")
        price_cents = None
        if isinstance(price_raw, int):
            # em muitos casos vem em "centavos * 1000" (ex.: 199900000 -> 199,90)
            # heurística: se for muito grande, divide por 1000
            if price_raw > 10_000_000:
                price_cents = int(price_raw // 1000)
            else:
                price_cents = int(price_raw)
        elif isinstance(price_raw, str) and price_raw.isdigit():
            pr = int(price_raw)
            price_cents = int(pr // 1000) if pr > 10_000_000 else pr

        if price_cents is None or price_cents < 10000:
            continue

        shopid = it.get("shopid")
        itemid = it.get("itemid")
        if shopid and itemid:
            link = f"https://shopee.com.br/product/{shopid}/{itemid}"
        else:
            link = url

        deals.append({
            "source": "Shopee",
            "title": title[:180],
            "url": normalize_url(link),
            "price_cents": price_cents,
        })

        if len(deals) >= 50:
            break

    return deals
