import os
from src.db import connect, upsert_deal
from src.bot import send_telegram_message
from src.scraper import scrape_atacadao, scrape_dpaschoal

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

DB_PATH = "tirebot.sqlite"

SOURCES = [
    ("https://www.atacadao.com.br/automotivo/pneus", "atacadao"),
    ("https://www.dpaschoal.com.br/pneus-e-camaras/carro-de-passeio", "dpaschoal"),
]

def format_price(price_cents):
    if price_cents is None:
        return "Preço não identificado"
    reais = price_cents // 100
    cents = price_cents % 100
    return f"R$ {reais:,}".replace(",", ".") + f",{cents:02d}"

def run():
    # Diagnóstico: confirma que o bot consegue enviar no grupo
    send_telegram_message(BOT_TOKEN, CHAT_ID, "TireBot: execução iniciada (teste de envio).")

    conn = connect(DB_PATH)

    new_items = []
    total_found = 0

    for url, source in SOURCES:
        if source == "atacadao":
            deals = scrape_atacadao(url)
        elif source == "dpaschoal":
            deals = scrape_dpaschoal(url)
        else:
            continue

        total_found += len(deals)

        for d in deals:
            if upsert_deal(conn, d):
                new_items.append(d)

    if new_items:
        lines = [f"Novas promoções encontradas: {len(new_items)} (varredura: {total_found})"]
        for d in new_items[:20]:
            lines.append(f"- {d['title']} | {format_price(d.get('price_cents'))}\n  {d['url']}")
        if len(new_items) > 20:
            lines.append(f"(+{len(new_items)-20} itens)")
        send_telegram_message(BOT_TOKEN, CHAT_ID, "\n".join(lines))
    else:
        send_telegram_message(
            BOT_TOKEN,
            CHAT_ID,
            f"TireBot: execução OK. Itens encontrados na varredura: {total_found}. Sem novidades."
        )

if __name__ == "__main__":
    run()
