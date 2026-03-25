import smtplib
from email.mime.text import MIMEText

import requests

from scraper.config import settings


def send_email(to: str, subject: str, body: str) -> None:
    if not all([settings.smtp_host, settings.smtp_user, settings.smtp_password]):
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to

    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.sendmail(settings.smtp_user, to, msg.as_string())


def send_telegram(chat_id: str, text: str) -> None:
    if not settings.telegram_bot_token:
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    resp.raise_for_status()


def notify_if_needed(price_changes: list[dict], notification_settings: dict) -> None:
    """
    Send notification if |delta_pct| >= threshold.
    price_changes: [{product_name, seller_name, delta_pct, latest_price}]
    notification_settings: {email, tg_chat_id, threshold}
    """
    threshold = notification_settings.get("threshold", 5)
    triggered = [c for c in price_changes if abs(c["delta_pct"]) >= threshold]

    if not triggered:
        return

    lines = []
    for change in triggered:
        sign = "+" if change["delta_pct"] > 0 else ""
        price_rub = change["latest_price"] / 100
        lines.append(
            f"{change['product_name']} | {change['seller_name']}: "
            f"{sign}{change['delta_pct']}% → {price_rub:.0f} ₽"
        )

    text = "🔔 Изменение цен:\n" + "\n".join(lines)

    if notification_settings.get("email"):
        send_email(
            to=notification_settings["email"],
            subject="Price Parser — изменение цен",
            body=text,
        )

    if notification_settings.get("tg_chat_id"):
        send_telegram(chat_id=notification_settings["tg_chat_id"], text=text)
