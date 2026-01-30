import os
import re
import time
from urllib.parse import quote_plus, urlparse, urlunparse

import requests

UA = "Mozilla/5.0 (compatible; TireBot/1.0)"
JINA_API_KEY = os.getenv("JINA_API_KEY")  # opcional

UNAVAILABLE_WORDS = [
    "indisponível", "indisponivel", "esgotado", "sem estoque", "fora de estoque",
    "produto indisponível", "não disponível", "nao disponivel"
]

def jina_headers():
    h = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    if JINA_API_KEY:
        h["Authorization"] = f"Bearer {JINA_API_KEY}"
    return h

def normalize_url(u: str) -> str:
    p = urlparse(u)
    # remove query/fragment para reduzir repetição
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))

def extract_urls(text: str, max_urls: int = 10) -> list[str]:
    urls = re.findall(r"https?://[^\s\)\]]+", text or "")
    seen = set()
    out = []
    for u in urls:
        u = u.strip().rstrip(".,;)")
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= max_urls:
            break
    return out

def contains_unavailable(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in UNAVAILABLE_WORDS)

def parse_prices_cents(text: str) -> list[int]:
    # captura todos "R$ x.xxx,yy"
    prices = re.findall(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", text or "")
    out = []
    for p in prices:
        m = re.search(r"R\$\s*([\d\.\,]+)", p)
        if not m:
            continue
        num = m.group(1).replace(".", "").replace(",", ".")
        try:
            out.append(int(round(float(num) * 100)))
        except:
            pass
    return out

def best_price_cents(text: str) -> int | None:
    """
    Preferência:
    - se tiver "no Pix"/"à vista", pega o menor desses
    - senão, pega o menor preço geral
    """
    t = text or ""
    pix_prices = []
    for m in re.finditer(r"(R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}).{0,25}(pix|à vista|a vista)", t, flags=re.I):
        pix_prices += parse_prices_cents(m.group(1))
    if pix_prices:
        return min(pix_prices)

    allp = parse_prices_cents(t)
    return min(allp) if allp else None

def jina_search(query: str, sites: list[str], max_urls: int = 8) -> list[str]:
    q = query + " " + " ".join([f"site:{s}" for s in sites])
    url = f"https://s.jina.ai/{quote_plus(q)}"
    r = requests.get(url, headers=jina_headers(), timeout=60)
    r.raise_for_status()
    return extract_urls(r.text, max_urls=max_urls)

def jina_read(url_to_read: str) -> str:
    url = "https://r.jina.ai/" + url_to_read
    r = requests.get(url, headers=jina_headers(), timeout=60)
    r.raise_for_status()
    return r.text

def polite_sleep():
    time.sleep(1.0)
