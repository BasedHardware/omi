import asyncio
import concurrent.futures
import threading
from datetime import datetime, time, timedelta

import pytz

import database.chat as chat_db
import database.conversations as conversations_db
import database.notifications as notification_db
from database.redis_db import try_acquire_daily_summary_lock
from models.notification_message import NotificationMessage
from models.conversation import Conversation
from utils.llm.external_integrations import get_conversation_summary, generate_comprehensive_daily_summary
from utils.notifications import send_bulk_notification, send_notification
from utils.webhooks import day_summary_webhook
import database.daily_summaries as daily_summaries_db


def should_run_job():
    """
    Check if the notification cron job should run.
    Always returns True since we now handle all hours dynamically.
    """
    return True


async def start_cron_job():
    """
    Main cron job entry point. Runs at the top of every UTC hour.
    """
    print(f'start_cron_job at UTC hour {datetime.now(pytz.utc).hour}')
    await send_daily_notification()
    await send_daily_summary_notification()


async def send_daily_summary_notification():
    """
    Send daily summary notifications to users based on their local hour preference.

    Groups timezones by their current local hour, then for each hour group,
    queries users in those timezones who have that hour preference.
    """
    try:
        # Group timezones by their current local hour
        timezones_by_hour = _get_timezones_grouped_by_hour()

        for target_hour, timezones in timezones_by_hour.items():
            # Get users in those timezones who want notifications at this hour
            users = await notification_db.get_users_for_daily_summary(timezones, target_hour)

            if users:
                print(f"Sending daily summary to {len(users)} users at local hour {target_hour}")
                await _send_bulk_summary_notification(users)

    except Exception as e:
        print(f"Error sending daily summary: {e}")
        return None


def _get_timezones_grouped_by_hour() -> dict[int, list[str]]:
    """Group all timezones by their current local hour."""
    timezones_by_hour = {}
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        current_hour = datetime.now(tz).hour
        if current_hour not in timezones_by_hour:
            timezones_by_hour[current_hour] = []
        timezones_by_hour[current_hour].append(tz_name)
    return timezones_by_hour


def _send_summary_notification(user_data: tuple):
    uid = user_data[0]
    user_tz_name = user_data[2] if len(user_data) > 2 else None

    # Calculate past 24 hours for conversation fetching
    # date_str is set based on current hour:
    #   - Before 12 PM (noon): use previous day's date
    #   - 12 PM or after: use current day's date
    start_date_utc = None
    end_date_utc = None
    date_str = None
    if user_tz_name:
        try:
            user_tz = pytz.timezone(user_tz_name)
            now_in_user_tz = datetime.now(user_tz)

            # Use past 24 hours for conversation range
            end_date_utc = now_in_user_tz.astimezone(pytz.utc)
            start_date_utc = (now_in_user_tz - timedelta(hours=24)).astimezone(pytz.utc)

            # Determine display date based on current hour
            if now_in_user_tz.hour < 12:
                # Before noon: show previous day
                display_date = now_in_user_tz.date() - timedelta(days=1)
            else:
                # Noon or after: show current day
                display_date = now_in_user_tz.date()
            date_str = display_date.strftime('%Y-%m-%d')
        except Exception as e:
            print(e)

    # Fallback to UTC if timezone not available
    if not start_date_utc or not end_date_utc:
        now_utc = datetime.now(pytz.utc)

        # Use past 24 hours for conversation range
        end_date_utc = now_utc
        start_date_utc = now_utc - timedelta(hours=24)

        # Determine display date based on current hour
        if now_utc.hour < 12:
            display_date = now_utc.date() - timedelta(days=1)
        else:
            display_date = now_utc.date()
        date_str = display_date.strftime('%Y-%m-%d')

    # Atomically acquire lock BEFORE expensive LLM work to prevent race condition
    if not try_acquire_daily_summary_lock(uid, date_str):
        return

    conversations_data = conversations_db.get_conversations(uid, start_date=start_date_utc, end_date=end_date_utc)
    if not conversations_data or len(conversations_data) == 0:
        return

    conversations = [Conversation(**convo_data) for convo_data in conversations_data]

    summary_data = generate_comprehensive_daily_summary(uid, conversations, date_str, start_date_utc, end_date_utc)

    # Store in database
    summary_id = daily_summaries_db.create_daily_summary(uid, summary_data)

    # Create notification with deep link to summary page
    daily_summary_title = f"{summary_data.get('day_emoji', '📅')} {summary_data.get('headline', 'Your Daily Summary')}"
    summary_body = summary_data.get('overview', 'Tap to see your daily summary')

    # Truncate body for notification if too long
    if len(summary_body) > 150:
        summary_body = summary_body[:147] + "..."

    ai_message = NotificationMessage(
        text=summary_body,
        from_integration='false',
        type='day_summary',
        notification_type='daily_summary',
        navigate_to=f"/daily-summary/{summary_id}",
    )

    # Also send webhook with the full summary data
    threading.Thread(target=day_summary_webhook, args=(uid, str(summary_data))).start()

    tokens = user_data[1] if len(user_data) > 1 else None
    send_notification(
        uid, daily_summary_title, summary_body, NotificationMessage.get_message_as_dict(ai_message), tokens=tokens
    )


async def _send_bulk_summary_notification(users: list):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        tasks = [loop.run_in_executor(pool, _send_summary_notification, user_tokens) for user_tokens in users]
        await asyncio.gather(*tasks)


async def send_daily_notification():
    try:
        morning_alert_title = "omi says"
        morning_alert_body = "Wear your omi and capture your conversations today."
        morning_target_time = "08:00"

        await _send_notification_for_time(morning_target_time, morning_alert_title, morning_alert_body)

    except Exception as e:
        print(e)
        print("Error sending message:", e)
        return None


async def _send_notification_for_time(target_time: str, title: str, body: str):
    user_in_time_zone = await _get_users_in_timezone(target_time)
    if not user_in_time_zone:
        print("No users found in time zone")
        return None
    await send_bulk_notification(user_in_time_zone, title, body)
    return user_in_time_zone


async def _get_users_in_timezone(target_time: str):
    timezones_in_time = _get_timezones_at_time(target_time)
    return await notification_db.get_users_token_in_timezones(timezones_in_time)


def _get_timezones_at_time(target_time):
    target_timezones = []
    for tz_name in pytz.all_timezones:
        tz = pytz.timezone(tz_name)
        current_time = datetime.now(tz).strftime("%H:%M")
        if current_time == target_time:
            target_timezones.append(tz_name)
    return target_timezones
