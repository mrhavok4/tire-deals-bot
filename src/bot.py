import requests

def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    r = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Telegram error {r.status_code}: {r.text}")
