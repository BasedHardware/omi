import asyncio
import concurrent.futures
import threading
from datetime import datetime, time

import pytz

import database.chat as chat_db
import database.conversations as conversations_db
import database.notifications as notification_db
from models.notification_message import NotificationMessage
from models.conversation import Conversation
from utils.llm.external_integrations import get_conversation_summary
from utils.notifications import send_bulk_notification, send_notification
from utils.webhooks import day_summary_webhook


async def start_cron_job():
    if should_run_job():
        print('start_cron_job')
        await send_daily_notification()
        await send_daily_summary_notification()


def should_run_job():
    current_utc = datetime.now(pytz.utc)
    target_hours = {8, 22}

    for tz in pytz.all_timezones:
        local_time = current_utc.astimezone(pytz.timezone(tz))
        if local_time.hour in target_hours and local_time.minute == 0:
            return True

    return False


async def send_daily_summary_notification():
    try:
        daily_summary_target_time = "22:00"
        timezones_in_time = _get_timezones_at_time(daily_summary_target_time)
        user_in_time_zone = await notification_db.get_users_id_in_timezones(timezones_in_time)
        if not user_in_time_zone:
            return None

        await _send_bulk_summary_notification(user_in_time_zone)
    except Exception as e:
        print(e)
        print("Error sending message:", e)
        return None


def _send_summary_notification(user_data: tuple):
    uid = user_data[0]
    user_tz_name = user_data[2] if len(user_data) > 2 else None

    # Note: user_data[1] was fcm_token, no longer needed
    daily_summary_title = "Here is your action plan for tomorrow"  # TODO: maybe include llm a custom message for this

    # Calculate user's day boundaries in their timezone, then convert to UTC for database query
    start_date_utc = None
    end_date_utc = None
    if user_tz_name:
        try:
            user_tz = pytz.timezone(user_tz_name)
            now_in_user_tz = datetime.now(user_tz)
            start_of_day_user_tz = user_tz.localize(datetime.combine(now_in_user_tz.date(), time.min))
            end_of_day_user_tz = now_in_user_tz
            start_date_utc = start_of_day_user_tz.astimezone(pytz.utc)
            end_date_utc = end_of_day_user_tz.astimezone(pytz.utc)
        except Exception as e:
            print(e)

    # Fallback to UTC if timezone not available
    if not start_date_utc or not end_date_utc:
        now_utc = datetime.now(pytz.utc)
        start_date_utc = datetime.combine(now_utc.date(), time.min).replace(tzinfo=pytz.utc)
        end_date_utc = now_utc

    conversations_data = conversations_db.get_conversations(
        uid, start_date=start_date_utc, end_date=start_date_utc
    )
    if not conversations_data or len(conversations_data) == 0:
        return

    conversations = [Conversation(**convo_data) for convo_data in conversations_data]
    summary = get_conversation_summary(uid, conversations)

    ai_message = NotificationMessage(
        text=summary,
        from_integration='false',
        type='day_summary',
        notification_type='daily_summary',
        navigate_to="/chat/omi",  # omi ~ no select
    )
    chat_db.add_summary_message(summary, uid)
    threading.Thread(target=day_summary_webhook, args=(uid, summary)).start()
    tokens = user_data[1] if len(user_data) > 1 else None
    send_notification(uid, daily_summary_title, summary, NotificationMessage.get_message_as_dict(ai_message), tokens=tokens)


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
