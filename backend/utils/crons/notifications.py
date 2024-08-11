import asyncio
import concurrent.futures
from datetime import datetime

import pytz

import database.notifications as notification_db
from routers.notifications import send_notification


async def start_cron_job():
    print('start_cron_job')
    await send_daily_notification()


async def send_daily_notification():
    try:
        morning_alert_title = "Don\'t forget to wear Friend today"
        morning_alert_body = "Wear your friend and capture your memories today."

        daily_summary_title = "Here is your action plan for tomorrow"
        daily_summary_body = "Check out your daily summary to see what you should do tomorrow."
        morning_target_time = "08:00"
        daily_summary_target_time = "22:00"

        await _send_notification_for_time(morning_target_time, morning_alert_title, morning_alert_body)
        await _send_notification_for_time(daily_summary_target_time, daily_summary_title, daily_summary_body)

    except Exception as e:
        print(e)
        print("Error sending message:", e)
        return None


async def _send_notification_for_time(target_time: str, title: str, body: str):
    user_in_time_zone = await _get_users_in_timezone(target_time)
    await _send_bulk_notification(user_in_time_zone, title, body)
    return user_in_time_zone


async def _get_users_in_timezone(target_time: str):
    timezones_in_time = _get_timezones_at_time(target_time)
    return await notification_db.get_users_in_timezones(timezones_in_time)


def _get_timezones_at_time(target_time):
    target_timezones = []
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        current_time = datetime.now(tz).strftime("%H:%M")
        if current_time == target_time:
            target_timezones.append(tz_name)
    return target_timezones


async def _send_bulk_notification(users: list, title: str, body: str):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        tasks = [
            loop.run_in_executor(pool, send_notification, token, title, body)
            for token in users
        ]
        await asyncio.gather(*tasks)
