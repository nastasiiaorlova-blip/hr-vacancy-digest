import os
import urllib.error
import urllib.parse
import urllib.request

TELEGRAM_MESSAGE_LIMIT = 4096


def send_message(text: str, token: str | None = None, chat_id: str | None = None) -> None:
    token = token or os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")

    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {error.code}: {body}") from error


def send_digest(messages: list[str], token: str | None = None, chat_id: str | None = None) -> None:
    for message in messages:
        if len(message) > TELEGRAM_MESSAGE_LIMIT:
            raise ValueError(
                f"Сообщение длиннее лимита Telegram ({len(message)} > {TELEGRAM_MESSAGE_LIMIT}); "
                "резать нужно на этапе сборки дайджеста, по границе вакансии"
            )
        send_message(message, token=token, chat_id=chat_id)
