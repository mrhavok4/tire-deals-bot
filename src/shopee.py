import re
import requests
from urllib.parse import urlparse, urlunparse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"

def normalize_url(u: str) -> str:
    p = urlparse(u)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))

def looks_like_kit(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"])

def scrape_shopee(query: str) -> list[dict]:
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
    deals = []

    for wrap in items:
        it = wrap.get("item_basic") or {}
        title = (it.get("name") or "").strip()
        if not title or "pneu" not in title.lower() or looks_like_kit(title):
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
