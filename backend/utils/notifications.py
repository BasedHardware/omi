import asyncio
import math
from firebase_admin import messaging, auth
import database.notifications as notification_db
from database.redis_db import (
    set_credit_limit_notification_sent,
    has_credit_limit_notification_been_sent,
    set_silent_user_notification_sent,
    has_silent_user_notification_been_sent,
)
from database.auth import get_user_from_uid
from .llm.notifications import (
    generate_notification_message,
    generate_credit_limit_notification,
    generate_silent_user_notification,
)


def send_notification(token: str, title: str, body: str, data: dict = None):
    print('send_notification')
    notification = messaging.Notification(title=title, body=body)
    message = messaging.Message(notification=notification, token=token)

    if data:
        message.data = data

    try:
        response = messaging.send(message)
        print('send_notification success:', response)
    except Exception as e:
        error_message = str(e)
        if "Requested entity was not found" in error_message:
            notification_db.remove_token(token)
        print('send_notification failed:', e)


async def send_subscription_paid_personalized_notification(user_id: str, data: dict = None):
    """Send a personalized notification to all user's devices when unlimited subscription is purchased"""
    # Get user's notification token
    token = notification_db.get_token_only(user_id)
    if not token:
        print(f"No notification token found for user {user_id}")
        return

    # Get user name from Firebase Auth
    try:
        user = auth.get_user(user_id)
        name = user.display_name
        if not name and user.email:
            name = user.email.split('@')[0].capitalize()
        if not name:
            name = "there"
    except Exception as e:
        print(f"Error getting user info from Firebase Auth: {e}")
        name = "there"

    # Generate welcome message for unlimited plan with user context
    title, body = await generate_notification_message(user_id, name, "unlimited")

    send_notification(token, "omi", body, data)


async def send_credit_limit_notification(user_id: str):
    """Send a personalized credit limit notification if not sent recently"""
    # Check if notification was sent recently (within 6 hours)
    if has_credit_limit_notification_been_sent(user_id):
        print(f"Credit limit notification already sent recently for user {user_id}")
        return

    # Get user's notification token
    token = notification_db.get_token_only(user_id)
    if not token:
        print(f"No notification token found for user {user_id}")
        return

    # Get user name from Firebase Auth
    try:
        user = auth.get_user(user_id)
        name = user.display_name
        if not name and user.email:
            name = user.email.split('@')[0].capitalize()
        if not name:
            name = "there"
    except Exception as e:
        print(f"Error getting user info from Firebase Auth: {e}")
        name = "there"

    # Generate personalized credit limit message
    title, body = await generate_credit_limit_notification(user_id, name)

    # Send notification
    send_notification(token, title, body)

    # Cache that notification was sent (6 hours TTL)
    set_credit_limit_notification_sent(user_id)
    print(f"Credit limit notification sent to user {user_id}")


async def send_silent_user_notification(user_id: str):
    """Send a notification if a basic-plan user is silent for too long."""
    # Check if notification was sent recently (within 24 hours)
    if has_silent_user_notification_been_sent(user_id):
        print(f"Silent user notification already sent recently for user {user_id}")
        return

    # Get user's notification token
    token = notification_db.get_token_only(user_id)
    if not token:
        print(f"No notification token found for user {user_id}")
        return

    # Get user name from Firebase Auth
    try:
        user = auth.get_user(user_id)
        name = user.display_name
        if not name and user.email:
            name = user.email.split('@')[0].capitalize()
        if not name:
            name = "there"
    except Exception as e:
        print(f"Error getting user info from Firebase Auth: {e}")
        name = "there"

    # Generate personalized credit limit message
    title, body = generate_silent_user_notification(name)

    # Send notification
    send_notification(token, title, body)

    # Cache that notification was sent (24 hours TTL)
    set_silent_user_notification_sent(user_id)
    print(f"Silent user notification sent to user {user_id}")


async def send_bulk_notification(user_tokens: list, title: str, body: str):
    try:
        batch_size = 500
        num_batches = math.ceil(len(user_tokens) / batch_size)

        def send_batch(batch_users):
            messages = [
                messaging.Message(notification=messaging.Notification(title=title, body=body), token=token)
                for token in batch_users
            ]
            return messaging.send_each(messages)

        tasks = []
        for i in range(num_batches):
            start = i * batch_size
            end = start + batch_size
            batch_users = user_tokens[start:end]
            task = asyncio.to_thread(send_batch, batch_users)
            tasks.append(task)

        await asyncio.gather(*tasks)

    except Exception as e:
        print("Error sending message:", e)


def send_app_review_reply_notification(
    reviewer_uid: str, app_owner_uid: str, reply_body: str, app_id: str, app_name: str
):
    """Sends a notification to a user when their app review receives a reply."""
    token = notification_db.get_token_only(reviewer_uid)
    if not token:
        return

    app_owner = get_user_from_uid(app_owner_uid)
    owner_name = app_owner.get('display_name', 'The developer') if app_owner else 'The developer'
    title = f'{owner_name} ({app_name})'
    body = reply_body
    data = {'app_id': app_id, 'type': 'app_review_reply', 'navigate_to': f'/apps/{app_id}'}
    send_notification(token, title, body, data)


def send_new_app_review_notification(
    app_owner_uid: str, reviewer_uid: str, app_id: str, app_name: str, review_body: str
):
    """Sends a notification to the app owner when a new review is submitted."""
    token = notification_db.get_token_only(app_owner_uid)
    if not token:
        return

    reviewer = get_user_from_uid(reviewer_uid)
    reviewer_name = reviewer.get('display_name', 'A user') if reviewer else 'A user'
    title = f'{reviewer_name} reviewed {app_name}'
    body = review_body
    data = {'app_id': app_id, 'type': 'new_app_review', 'navigate_to': f'/apps/{app_id}'}
    send_notification(token, title, body, data)


def send_action_item_data_message(user_id: str, action_item_id: str, description: str, due_at: str):
    """
    Sends a data-only FCM message for action item reminder scheduling.
    The app receives this in the background and schedules a local notification.

    Args:
        user_id: The user's Firebase UID
        action_item_id: The action item ID
        description: The action item description
        due_at: ISO format datetime string for when the action item is due
    """
    token = notification_db.get_token_only(user_id)
    if not token:
        print(f"No notification token found for user {user_id}")
        return

    # Data-only message
    # This allows the app to handle it in background and schedule local notification
    data = {
        'type': 'action_item_reminder',
        'action_item_id': action_item_id,
        'description': description,
        'due_at': due_at,
    }

    message = messaging.Message(
        data=data,
        token=token,
        # Set high priority to ensure delivery even when app is in background
        android=messaging.AndroidConfig(priority='high'),
        # iOS requires specific headers for background data-only messages
        apns=messaging.APNSConfig(
            headers={
                'apns-push-type': 'background',
                'apns-priority': '5',
                'apns-topic': 'com.friend-app-with-wearable.ios12',
            },
            payload=messaging.APNSPayload(aps=messaging.Aps(content_available=True)),
        ),
    )

    try:
        response = messaging.send(message)
    except Exception as e:
        error_message = str(e)
        if "Requested entity was not found" in error_message:
            notification_db.remove_token(token)
        print(f'Failed to send action item data message: {e}')


def send_action_item_update_message(user_id: str, action_item_id: str, description: str, due_at: str):
    """
    Sends a data-only FCM message when an action item is updated.
    The app receives this and reschedules the local notification.
    """
    token = notification_db.get_token_only(user_id)
    if not token:
        print(f"No notification token found for user {user_id}")
        return

    data = {
        'type': 'action_item_update',
        'action_item_id': action_item_id,
        'description': description,
        'due_at': due_at,
    }

    message = messaging.Message(
        data=data,
        token=token,
        android=messaging.AndroidConfig(priority='high'),
        # iOS requires specific headers for background data-only messages
        apns=messaging.APNSConfig(
            headers={
                'apns-push-type': 'background',
                'apns-priority': '5',
                'apns-topic': 'com.friend-app-with-wearable.ios12',
            },
            payload=messaging.APNSPayload(aps=messaging.Aps(content_available=True)),
        ),
    )

    try:
        response = messaging.send(message)
    except Exception as e:
        error_message = str(e)
        if "Requested entity was not found" in error_message:
            notification_db.remove_token(token)
        print(f'Failed to send action item update message: {e}')


def send_action_item_deletion_message(user_id: str, action_item_id: str):
    """
    Sends a data-only FCM message when an action item is deleted.
    The app receives this and cancels the scheduled local notification.
    """
    token = notification_db.get_token_only(user_id)
    if not token:
        print(f"No notification token found for user {user_id}")
        return

    data = {
        'type': 'action_item_delete',
        'action_item_id': action_item_id,
    }

    message = messaging.Message(
        data=data,
        token=token,
        android=messaging.AndroidConfig(priority='high'),
        # iOS requires specific headers for background data-only messages
        apns=messaging.APNSConfig(
            headers={
                'apns-push-type': 'background',
                'apns-priority': '5',
                'apns-topic': 'com.friend-app-with-wearable.ios12',
            },
            payload=messaging.APNSPayload(aps=messaging.Aps(content_available=True)),
        ),
    )

    try:
        response = messaging.send(message)
    except Exception as e:
        error_message = str(e)
        if "Requested entity was not found" in error_message:
            notification_db.remove_token(token)
        print(f'Failed to send action item deletion message: {e}')
