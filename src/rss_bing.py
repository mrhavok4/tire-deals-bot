import re
import time
import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; TireBot/1.0)"

def polite_sleep():
    time.sleep(1.0)

def fetch_bing_rss(query: str) -> list[dict]:
    url = f"https://www.bing.com/news/search?q={query}&format=rss"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "xml")

    out = []
    for it in soup.find_all("item"):
        title = (it.title.get_text(strip=True) if it.title else "")
        link = (it.link.get_text(strip=True) if it.link else "")
        desc = (it.description.get_text(" ", strip=True) if it.description else "")
        out.append({"title": title, "url": link, "desc": desc})
    return out

def price_from_text_cents(text: str):
    prices = re.findall(r"R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}", text or "")
    cents = []
    for p in prices:
        num = p.replace("R$", "").strip().replace(".", "").replace(",", ".")
        try:
            cents.append(int(round(float(num) * 100)))
        except:
            pass
    return min(cents) if cents else None

def detect_aro(text: str):
    m = re.search(r"\bR\s*(13|14|15)\b", (text or "").upper())
    return int(m.group(1)) if m else None

def looks_like_kit(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ["kit", "jogo", "4 pneus", "2 pneus", "par", "combo"])

def looks_unavailable(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ["indisponível", "esgotado", "sem estoque", "fora de estoque"])
