"""Tests for email and Telegram notification module."""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from api.notifier import send_email, send_telegram, check_price_alerts


class TestSendEmail:
    """Test email sending via SMTP."""

    @patch("api.notifier.smtplib.SMTP_SSL")
    @patch("api.notifier.settings")
    def test_sends_email_with_correct_params(self, mock_settings, mock_smtp_cls):
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 465
        mock_settings.smtp_user = "sender@test.com"
        mock_settings.smtp_password = "secret"

        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        send_email("user@example.com", "Тема", "Текст письма")

        mock_smtp_cls.assert_called_once_with("smtp.test.com", 465)
        mock_smtp.login.assert_called_once_with("sender@test.com", "secret")
        mock_smtp.send_message.assert_called_once()
        msg = mock_smtp.send_message.call_args[0][0]
        assert msg["To"] == "user@example.com"
        assert msg["Subject"] == "Тема"
        assert "Текст письма" in msg.get_payload(decode=True).decode()

    @patch("api.notifier.smtplib.SMTP_SSL")
    @patch("api.notifier.settings")
    def test_returns_false_if_smtp_not_configured(self, mock_settings, mock_smtp_cls):
        mock_settings.smtp_host = ""
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""

        result = send_email("user@example.com", "Тема", "Текст")

        assert result is False
        mock_smtp_cls.assert_not_called()

    @patch("api.notifier.smtplib.SMTP_SSL")
    @patch("api.notifier.settings")
    def test_returns_false_on_smtp_error(self, mock_settings, mock_smtp_cls):
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_port = 465
        mock_settings.smtp_user = "sender@test.com"
        mock_settings.smtp_password = "secret"

        mock_smtp_cls.side_effect = smtplib.SMTPException("Connection refused")

        result = send_email("user@example.com", "Тема", "Текст")

        assert result is False


class TestSendTelegram:
    """Test Telegram message sending."""

    @patch("api.notifier.httpx.post")
    @patch("api.notifier.settings")
    def test_sends_message_with_correct_params(self, mock_settings, mock_post):
        mock_settings.telegram_bot_token = "123:ABC"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        result = send_telegram("531342852", "Тестовое сообщение")

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "123:ABC" in call_kwargs[0][0]
        assert call_kwargs[1]["json"]["chat_id"] == "531342852"
        assert call_kwargs[1]["json"]["text"] == "Тестовое сообщение"

    @patch("api.notifier.httpx.post")
    @patch("api.notifier.settings")
    def test_returns_false_if_token_not_configured(self, mock_settings, mock_post):
        mock_settings.telegram_bot_token = ""

        result = send_telegram("531342852", "Текст")

        assert result is False
        mock_post.assert_not_called()

    @patch("api.notifier.httpx.post")
    @patch("api.notifier.settings")
    def test_returns_false_on_http_error(self, mock_settings, mock_post):
        mock_settings.telegram_bot_token = "123:ABC"
        mock_post.side_effect = Exception("Connection error")

        result = send_telegram("531342852", "Текст")

        assert result is False


class TestCheckPriceAlerts:
    """Test price change detection and alert triggering."""

    def test_no_alert_when_price_unchanged(self, db):
        """If old price == new price, no alert."""
        from api.models import Product, Seller, PriceHistory, NotificationSettings

        product = Product(name="TV", wb_article="123", wb_url="http://wb/123")
        db.add(product)
        db.flush()

        seller = Seller(product_id=product.id, seller_name="Shop", seller_id="shop")
        db.add(seller)
        db.flush()

        db.add(PriceHistory(seller_id=seller.id, price=10000))
        db.add(PriceHistory(seller_id=seller.id, price=10000))

        ns = NotificationSettings(email="user@test.com", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email") as mock_email, \
             patch("api.notifier.send_telegram") as mock_tg:
            alerts = check_price_alerts(db)
            assert alerts == 0
            mock_email.assert_not_called()
            mock_tg.assert_not_called()

    def test_alert_sent_when_price_drops_over_threshold(self, db):
        """If price drops >= threshold%, email and telegram are sent."""
        from api.models import Product, Seller, PriceHistory, NotificationSettings
        from datetime import datetime, timezone, timedelta

        product = Product(name="Телевизор Haier 55", wb_article="555", wb_url="http://wb/555")
        db.add(product)
        db.flush()

        seller = Seller(product_id=product.id, seller_name="Haier Official", seller_id="haier")
        db.add(seller)
        db.flush()

        old_time = datetime.now(timezone.utc) - timedelta(hours=13)
        new_time = datetime.now(timezone.utc)
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=9000, recorded_at=new_time))

        ns = NotificationSettings(email="user@test.com", tg_chat_id="531342852", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email", return_value=True) as mock_email, \
             patch("api.notifier.send_telegram", return_value=True) as mock_tg:
            alerts = check_price_alerts(db)
            assert alerts == 1
            mock_email.assert_called_once()
            mock_tg.assert_called_once()
            # Check content
            assert "Телевизор Haier 55" in mock_email.call_args[0][2]
            assert "Телевизор Haier 55" in mock_tg.call_args[0][1]

    def test_no_alert_when_change_below_threshold(self, db):
        """If price change < threshold%, no alert."""
        from api.models import Product, Seller, PriceHistory, NotificationSettings
        from datetime import datetime, timezone, timedelta

        product = Product(name="TV", wb_article="777", wb_url="http://wb/777")
        db.add(product)
        db.flush()

        seller = Seller(product_id=product.id, seller_name="Shop", seller_id="shop")
        db.add(seller)
        db.flush()

        old_time = datetime.now(timezone.utc) - timedelta(hours=13)
        new_time = datetime.now(timezone.utc)
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=9800, recorded_at=new_time))

        ns = NotificationSettings(email="user@test.com", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email") as mock_email, \
             patch("api.notifier.send_telegram") as mock_tg:
            alerts = check_price_alerts(db)
            assert alerts == 0
            mock_email.assert_not_called()
            mock_tg.assert_not_called()

    def test_no_alert_when_no_channels_configured(self, db):
        """If email and tg_chat_id are both empty, skip alerting."""
        from api.models import Product, Seller, PriceHistory, NotificationSettings
        from datetime import datetime, timezone, timedelta

        product = Product(name="TV", wb_article="888", wb_url="http://wb/888")
        db.add(product)
        db.flush()

        seller = Seller(product_id=product.id, seller_name="Shop", seller_id="shop")
        db.add(seller)
        db.flush()

        old_time = datetime.now(timezone.utc) - timedelta(hours=13)
        new_time = datetime.now(timezone.utc)
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=8000, recorded_at=new_time))

        ns = NotificationSettings(email="", tg_chat_id="", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email") as mock_email, \
             patch("api.notifier.send_telegram") as mock_tg:
            alerts = check_price_alerts(db)
            assert alerts == 0
            mock_email.assert_not_called()
            mock_tg.assert_not_called()

    def test_alert_on_price_increase(self, db):
        """Alert also fires on price increase >= threshold%."""
        from api.models import Product, Seller, PriceHistory, NotificationSettings
        from datetime import datetime, timezone, timedelta

        product = Product(name="TV", wb_article="999", wb_url="http://wb/999")
        db.add(product)
        db.flush()

        seller = Seller(product_id=product.id, seller_name="Shop", seller_id="shop")
        db.add(seller)
        db.flush()

        old_time = datetime.now(timezone.utc) - timedelta(hours=13)
        new_time = datetime.now(timezone.utc)
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=11000, recorded_at=new_time))

        ns = NotificationSettings(email="user@test.com", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email", return_value=True) as mock_email, \
             patch("api.notifier.send_telegram") as mock_tg:
            alerts = check_price_alerts(db)
            assert alerts == 1

    def test_telegram_only_when_no_email(self, db):
        """If only tg_chat_id is set (no email), telegram alert still fires."""
        from api.models import Product, Seller, PriceHistory, NotificationSettings
        from datetime import datetime, timezone, timedelta

        product = Product(name="TV", wb_article="111", wb_url="http://wb/111")
        db.add(product)
        db.flush()

        seller = Seller(product_id=product.id, seller_name="Shop", seller_id="shop")
        db.add(seller)
        db.flush()

        old_time = datetime.now(timezone.utc) - timedelta(hours=13)
        new_time = datetime.now(timezone.utc)
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=8000, recorded_at=new_time))

        ns = NotificationSettings(email="", tg_chat_id="531342852", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email") as mock_email, \
             patch("api.notifier.send_telegram", return_value=True) as mock_tg:
            alerts = check_price_alerts(db)
            assert alerts == 1
            mock_email.assert_not_called()
            mock_tg.assert_called_once()
