import inspect

import database.notifications as notification_db


def test_timezone_notification_reads_are_synchronous_empty_safe_leaves() -> None:
    calls = [
        (notification_db.get_users_token_in_timezones, ([],)),
        (notification_db.get_users_id_in_timezones, ([],)),
        (notification_db.get_users_for_daily_summary, ([], 22)),
    ]

    for func, args in calls:
        assert not inspect.iscoroutinefunction(func)
        assert func(*args) == []
