"""
Price change notification module.

Detects price changes exceeding the configured threshold
and sends alerts via email (SMTP) and Telegram Bot API.
"""

import logging
import smtplib
from email.mime.text import MIMEText

import httpx
from sqlalchemy.orm import Session

from api.config import settings
from api.models import NotificationSettings, PriceHistory, Product, Seller

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via SMTP_SSL. Returns True on success, False on failure."""
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        logger.warning("SMTP not configured, skipping email")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject

    try:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info(f"Email sent to {to}: {subject}")
        return True
    except Exception:
        logger.exception(f"Failed to send email to {to}")
        return False


def send_telegram(chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, skipping")
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    try:
        resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info(f"Telegram message sent to {chat_id}")
            return True
        logger.error(f"Telegram API error: {resp.text}")
        return False
    except Exception:
        logger.exception(f"Failed to send Telegram message to {chat_id}")
        return False


def check_price_alerts(db: Session) -> int:
    """
    Compare the two most recent prices for each seller.
    If the change exceeds the threshold, send alerts via email and/or Telegram.
    Returns the number of alerts sent.
    """
    ns = db.query(NotificationSettings).first()
    if not ns:
        return 0

    has_email = bool(ns.email)
    has_tg = bool(ns.tg_chat_id)

    if not has_email and not has_tg:
        return 0

    threshold = ns.threshold or 5
    alerts_sent = 0

    sellers = db.query(Seller).all()
    for seller in sellers:
        recent = (
            db.query(PriceHistory)
            .filter(PriceHistory.seller_id == seller.id)
            .order_by(PriceHistory.recorded_at.desc())
            .limit(2)
            .all()
        )

        if len(recent) < 2:
            continue

        new_price = recent[0].price
        old_price = recent[1].price

        if old_price == 0:
            continue

        change_pct = abs((new_price - old_price) / old_price) * 100

        if change_pct < threshold:
            continue

        product = db.query(Product).filter(Product.id == seller.product_id).first()
        product_name = product.name if product else "Неизвестный товар"

        direction = "снизилась" if new_price < old_price else "выросла"
        sign = "-" if new_price < old_price else "+"

        body = (
            f"Цена на товар «{product_name}» {direction} на {change_pct:.1f}%\n\n"
            f"Продавец: {seller.seller_name}\n"
            f"Старая цена: {old_price:,} ₽\n"
            f"Новая цена: {new_price:,} ₽\n"
            f"Изменение: {sign}{abs(new_price - old_price):,} ₽ ({sign}{change_pct:.1f}%)\n"
        )

        subject = f"WB Price Alert: {product_name} ({sign}{change_pct:.1f}%)"

        sent = False
        if has_email:
            sent = send_email(ns.email, subject, body) or sent
        if has_tg:
            sent = send_telegram(ns.tg_chat_id, body) or sent

        if sent:
            alerts_sent += 1

    return alerts_sent
