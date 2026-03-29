"""Tests for email notification module."""
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from api.notifier import send_email, check_price_alerts


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

        # Two records with same price
        db.add(PriceHistory(seller_id=seller.id, price=10000))
        db.add(PriceHistory(seller_id=seller.id, price=10000))

        ns = NotificationSettings(email="user@test.com", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email") as mock_send:
            alerts = check_price_alerts(db)
            assert alerts == 0
            mock_send.assert_not_called()

    def test_alert_sent_when_price_drops_over_threshold(self, db):
        """If price drops >= threshold%, email is sent."""
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
        # Old price 10000, new price 9000 → -10% change
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=9000, recorded_at=new_time))

        ns = NotificationSettings(email="user@test.com", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email", return_value=True) as mock_send:
            alerts = check_price_alerts(db)
            assert alerts == 1
            mock_send.assert_called_once()
            # Check email contains product name and price info
            call_args = mock_send.call_args
            assert "user@test.com" == call_args[0][0]
            assert "Телевизор Haier 55" in call_args[0][2]

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
        # Old 10000, new 9800 → -2% (below 5% threshold)
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=9800, recorded_at=new_time))

        ns = NotificationSettings(email="user@test.com", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email") as mock_send:
            alerts = check_price_alerts(db)
            assert alerts == 0
            mock_send.assert_not_called()

    def test_no_alert_when_no_email_configured(self, db):
        """If email is empty in settings, skip alerting."""
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

        ns = NotificationSettings(email="", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email") as mock_send:
            alerts = check_price_alerts(db)
            assert alerts == 0
            mock_send.assert_not_called()

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
        # 10000 → 11000 = +10%
        db.add(PriceHistory(seller_id=seller.id, price=10000, recorded_at=old_time))
        db.add(PriceHistory(seller_id=seller.id, price=11000, recorded_at=new_time))

        ns = NotificationSettings(email="user@test.com", threshold=5)
        db.add(ns)
        db.commit()

        with patch("api.notifier.send_email", return_value=True) as mock_send:
            alerts = check_price_alerts(db)
            assert alerts == 1
