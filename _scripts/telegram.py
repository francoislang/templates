import requests
import config


def send(text: str) -> None:
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }, timeout=10)
