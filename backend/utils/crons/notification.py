import pytz
import asyncio
import concurrent.futures


from utils.redis_utils import get_user_token, get_user_timezone, get_all_user_timezones
from datetime import datetime
from routers.notifications import send_notification


async def start_cron_job():
    await send_daily_notification()


async def send_daily_notification():
    try:
        morning_users, daily_summary_users = get_users_for_notification()
        morning_alert_title = "Don\'t forget to wear Friend today"
        morning_alert_body = "Wear your friend and capture your memories today."

        daily_summary_title = "Here is your action plan for tomorrow"
        daily_summary_body = "Check out your daily summary to see what you should do tomorrow."


        await send_bulk_notification(morning_users, morning_alert_title, morning_alert_body)
        await send_bulk_notification(daily_summary_users, daily_summary_title, daily_summary_body)
    except Exception as e:
        print("Error sending message:", e)
        return None


def get_users_for_notification():

    morning_target_time = "08:00"
    daily_summary_target_time = "22:00"

    morning_users = []
    daily_summary_users = []

    user_keys = get_all_user_timezones()

    for user_key in user_keys:

        uid = user_key.decode().split(':')[1]
        timezone = get_user_timezone(uid)
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz).strftime("%H:%M")

        if current_time == morning_target_time:
            morning_users.append(uid)
        elif current_time == daily_summary_target_time:
            daily_summary_users.append(uid)

    return morning_users, daily_summary_users


def send_user_notification(uid: str, title: str, body: str):
    token = get_user_token(uid)
    send_notification(token, title, body)


async def send_bulk_notification(users: list, title: str, body: str):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        tasks = [
            loop.run_in_executor(pool, send_user_notification, uid, title, body)
            for uid in users
        ]
        await asyncio.gather(*tasks)
