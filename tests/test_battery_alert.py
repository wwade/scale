"""Tests for `build_battery_alert_message`.

Pure helper, so we just check subject, headers, and body content.
"""

from datetime import datetime
from email.mime.text import MIMEText

from monitor import build_battery_alert_message

FIXED_NOW = datetime(2026, 5, 11, 12, 34, 56)


def _body(message: MIMEText) -> str:
    return message.get_payload()


def test_message_is_mimetext_with_headers():
    message = build_battery_alert_message(18.4, 20.0, "alerts@example.com", now=FIXED_NOW)

    assert isinstance(message, MIMEText)
    assert message["to"] == "alerts@example.com"
    assert message["subject"] == "Low Battery Alert: Acaia Scale"


def test_body_contains_battery_threshold_and_timestamp():
    message = build_battery_alert_message(18.4, 20.0, "alerts@example.com", now=FIXED_NOW)
    body = _body(message)

    assert "Battery Level: 18.4%" in body
    assert "Alert Threshold: 20.0%" in body
    assert "Timestamp: 2026-05-11 12:34:56" in body


def test_body_includes_mac_when_provided():
    message = build_battery_alert_message(
        12.0,
        20.0,
        "alerts@example.com",
        mac_address="AA:BB:CC:DD:EE:FF",
        now=FIXED_NOW,
    )
    body = _body(message)

    assert "Scale MAC Address: AA:BB:CC:DD:EE:FF" in body


def test_body_omits_mac_when_absent():
    message = build_battery_alert_message(12.0, 20.0, "alerts@example.com", now=FIXED_NOW)
    body = _body(message)

    assert "Scale MAC Address" not in body


def test_now_defaults_to_current_time():
    before = datetime.now()
    message = build_battery_alert_message(12.0, 20.0, "alerts@example.com")
    after = datetime.now()

    body = _body(message)
    # The body should have *some* timestamp line that parses as a datetime
    # between `before` and `after`.
    timestamp_line = next(line for line in body.splitlines() if line.startswith("Timestamp: "))
    stamped = datetime.strptime(timestamp_line.removeprefix("Timestamp: "), "%Y-%m-%d %H:%M:%S")
    # strftime drops sub-second precision, so widen the bounds.
    assert before.replace(microsecond=0) <= stamped <= after.replace(microsecond=0)
