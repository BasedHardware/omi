from utils.other.notifications import should_send_wear_device_reminder


def test_daily_wear_reminder_is_disabled():
    assert should_send_wear_device_reminder() is False
