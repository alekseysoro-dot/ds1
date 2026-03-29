"""
Price change notification module.

Detects price changes exceeding the configured threshold
and sends email alerts to the configured recipient.
"""

import logging
import smtplib
from email.mime.text import MIMEText

from sqlalchemy import func
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


def check_price_alerts(db: Session) -> int:
    """
    Compare the two most recent prices for each seller.
    If the change exceeds the threshold, send an email alert.
    Returns the number of alerts sent.
    """
    ns = db.query(NotificationSettings).first()
    if not ns or not ns.email:
        return 0

    threshold = ns.threshold or 5
    alerts_sent = 0

    sellers = db.query(Seller).all()
    for seller in sellers:
        # Get the two most recent price records for this seller
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

        if send_email(ns.email, subject, body):
            alerts_sent += 1

    return alerts_sent
