import re
import json
import time
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus, urlparse, urlunparse

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"

def polite_sleep():
    time.sleep(0.8)

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

def looks_like_kit(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"])

def scrape_shopee(query: str) -> List[Dict[str, Any]]:
    url = "https://shopee.com.br/api/v4/search/search_items"
    params = {
        "by": "relevancy",
        "keyword": query,
        "limit": 50,
        "newest": 0,
        "order": "desc",
        "page_type": "search",
        "scenario": "PAGE_GLOBAL_SEARCH",
        "version": 2,
    }
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Referer": "https://shopee.com.br/",
    }

    r = requests.get(url, params=params, headers=headers, timeout=30)
    if r.status_code in (401, 403, 418, 429):
        return []
    r.raise_for_status()

    data = r.json()
    items = (data.get("items") or [])
    deals: List[Dict[str, Any]] = []

    for wrap in items:
        it = wrap.get("item_basic") or {}
        title = (it.get("name") or "").strip()
        if not title or "pneu" not in title.lower():
            continue
        if looks_like_kit(title):
            continue

        shopid = it.get("shopid")
        itemid = it.get("itemid")
        if not shopid or not itemid:
            continue

        price_raw = it.get("price_min") or it.get("price") or it.get("price_max")
        if not isinstance(price_raw, int):
            continue

        price_cents = int(price_raw // 1000)
        if price_cents < 10000:
            continue

        deals.append({
            "source": "Shopee",
            "title": title[:180],
            "url": normalize_url(f"https://shopee.com.br/product/{shopid}/{itemid}"),
            "price_cents": price_cents,
        })

    return deals
