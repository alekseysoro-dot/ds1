# tests/scraper/test_notifier.py
import pytest
from unittest.mock import patch, MagicMock


def test_send_email_called_with_correct_args():
    from scraper.notifier import send_email

    with patch("scraper.notifier.settings") as mock_settings:
        mock_settings.smtp_host = "smtp.test.com"
        mock_settings.smtp_user = "test@test.com"
        mock_settings.smtp_password = "pass"
        mock_settings.smtp_port = 465

        with patch("scraper.notifier.smtplib.SMTP_SSL") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__ = lambda s: mock_smtp
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

            send_email(
                to="user@example.com",
                subject="Тест",
                body="Цена изменилась",
            )

    mock_smtp.sendmail.assert_called_once()


def test_send_telegram_called():
    from scraper.notifier import send_telegram

    with patch("scraper.notifier.settings") as mock_settings:
        mock_settings.telegram_bot_token = "fake-token"

        with patch("scraper.notifier.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = lambda: None
            send_telegram(chat_id="123456", text="Тест уведомление")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "123456" in str(call_kwargs)


def test_check_and_notify_triggers_when_threshold_exceeded(mocker):
    from scraper import notifier

    mocker.patch.object(notifier, "send_email")
    mocker.patch.object(notifier, "send_telegram")

    price_changes = [
        {"product_name": "Телефон", "seller_name": "ООО А", "delta_pct": 15.0, "latest_price": 90000},
    ]
    settings = {"email": "user@example.com", "tg_chat_id": "123", "threshold": 5}

    notifier.notify_if_needed(price_changes, settings)

    notifier.send_email.assert_called_once()
    notifier.send_telegram.assert_called_once()


def test_check_and_notify_silent_when_below_threshold(mocker):
    from scraper import notifier

    mocker.patch.object(notifier, "send_email")
    mocker.patch.object(notifier, "send_telegram")

    price_changes = [
        {"product_name": "Телефон", "seller_name": "ООО А", "delta_pct": 2.0, "latest_price": 90000},
    ]
    settings = {"email": "user@example.com", "tg_chat_id": "123", "threshold": 5}

    notifier.notify_if_needed(price_changes, settings)

    notifier.send_email.assert_not_called()
    notifier.send_telegram.assert_not_called()
