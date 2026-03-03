import requests
from typing import List, Dict, Any

SERP_ENDPOINT = "https://serpapi.com/search.json"

def serpapi_shopping(query: str, api_key: str) -> List[Dict[str, Any]]:
    params = {
        "engine": "google_shopping",
        "q": query,
        "hl": "pt",
        "gl": "br",
        "api_key": api_key,
        "num": 20,
    }
    r = requests.get(SERP_ENDPOINT, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    out = []
    for it in data.get("shopping_results", []):
        price = it.get("extracted_price")
        if price is None:
            continue
        out.append({
            "source": it.get("source", "GoogleShopping"),
            "title": it.get("title", "")[:180],
            "url": it.get("link"),
            "price_cents": int(price * 100),
        })
    return out
