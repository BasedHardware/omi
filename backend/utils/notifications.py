import asyncio
import hashlib
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

# iOS bundle ID for APNs
IOS_BUNDLE_ID = 'com.friend-app-with-wearable.ios12'

# Error codes that indicate a token is permanently invalid
PERMANENT_FAILURE_CODES = frozenset(
    [
        'UNREGISTERED',  # App uninstalled
        'INVALID_REGISTRATION_TOKEN',  # Token format invalid
    ]
)


def _generate_tag(content: str) -> str:
    """Generate a 16-char hash tag for deduplication."""
    return hashlib.md5(content.encode()).hexdigest()[:16]


def _generate_notification_tag(user_id: str, title: str, body: str, data: dict = None) -> str:
    """Generate a tag for notification deduplication based on content."""
    content = f"{user_id}:{title}:{body}"
    if data:
        unique_id = data.get('action_item_id') or data.get('app_id') or data.get('type', '')
        content += f":{unique_id}"
    return _generate_tag(content)


def _build_android_config(tag: str, priority: str = 'normal', is_data_only: bool = False) -> messaging.AndroidConfig:
    """Build Android configuration with deduplication."""
    config_kwargs = {
        'collapse_key': tag,
        'priority': priority,
    }
    # Only add notification config if not data-only (Android shows empty notification otherwise)
    if not is_data_only:
        config_kwargs['notification'] = messaging.AndroidNotification(tag=tag)
    return messaging.AndroidConfig(**config_kwargs)


def _build_apns_config(tag: str, is_background: bool = False) -> messaging.APNSConfig:
    """Build APNs configuration with deduplication."""
    headers = {'apns-collapse-id': tag}

    if is_background:
        headers.update(
            {
                'apns-push-type': 'background',
                'apns-priority': '5',
                'apns-topic': IOS_BUNDLE_ID,
            }
        )
        return messaging.APNSConfig(
            headers=headers,
            payload=messaging.APNSPayload(aps=messaging.Aps(content_available=True)),
        )

    return messaging.APNSConfig(headers=headers)


def _build_webpush_config(tag: str, title: str = None, body: str = None, link: str = None) -> messaging.WebpushConfig:
    """Build WebPush configuration for browser notifications.

    Note: WebpushNotification must explicitly include title/body because
    browsers use webpush.notification instead of the top-level notification
    when the webpush block is present.

    fcm_options.link must be an absolute HTTPS URL - relative paths will cause
    FCM to reject the entire message batch with 'WebpushFCMOptions.link must be a HTTPS URL'.
    """
    config_kwargs = {
        'headers': {
            'Topic': tag,  # For deduplication
            'Urgency': 'high',
        },
        'notification': messaging.WebpushNotification(
            title=title,
            body=body,
            icon='/logo.png',
        ),
    }

    # Only include fcm_options if link is a valid HTTPS URL
    if link and link.startswith('https://'):
        config_kwargs['fcm_options'] = messaging.WebpushFCMOptions(link=link)

    return messaging.WebpushConfig(**config_kwargs)


def _build_message(
    token: str,
    tag: str,
    notification: messaging.Notification = None,
    data: dict = None,
    is_background: bool = False,
    priority: str = 'normal',
) -> messaging.Message:
    """Build a complete FCM message with proper platform configs."""
    # Extract title/body for webpush config (browsers need explicit values)
    title = notification.title if notification else None
    body = notification.body if notification else None
    # Extract navigate_to for webpush click-through link
    link = data.get('navigate_to') if data else None

    return messaging.Message(
        token=token,
        notification=notification,
        data=data,
        android=_build_android_config(tag, priority, is_data_only=(notification is None)),
        apns=_build_apns_config(tag, is_background),
        webpush=_build_webpush_config(tag, title, body, link),
    )


def _send_to_user(
    user_id: str,
    tag: str,
    notification: messaging.Notification = None,
    data: dict = None,
    is_background: bool = False,
    priority: str = 'normal',
    tokens: list = None,
) -> int:
    """Send a message to all user's devices using batch send. Returns count of successful sends."""
    if tokens is None:
        tokens = notification_db.get_all_tokens(user_id)
    if not tokens:
        print(f"No tokens found for user {user_id}")
        return 0

    # Build messages for all tokens
    messages = [_build_message(token, tag, notification, data, is_background, priority) for token in tokens]

    try:
        response = messaging.send_each(messages)

        # Collect invalid tokens and count successes
        invalid_tokens = []
        success_count = 0

        for idx, result in enumerate(response.responses):
            if result.success:
                success_count += 1
            elif result.exception:
                error_code = getattr(result.exception, 'code', None)
                if error_code in PERMANENT_FAILURE_CODES:
                    invalid_tokens.append(tokens[idx])
                    print(f'Invalid token removed - Error: {error_code}')
                else:
                    print(f'FCM send failed: {result.exception}({error_code})')

        # Remove invalid tokens in bulk
        if invalid_tokens:
            notification_db.remove_bulk_tokens(invalid_tokens)

        print(f'FCM batch send: {success_count}/{len(tokens)} successful')
        return success_count

    except Exception as e:
        print(f'FCM batch send error: {e}')
        return 0


def send_notification(user_id: str, title: str, body: str, data: dict = None, tokens: list = None):
    """Send notification to all user's devices. Optionally pass pre-fetched tokens to avoid DB lookup."""
    print(f'send_notification to user {user_id}')
    tag = _generate_notification_tag(user_id, title, body, data)
    notification = messaging.Notification(title=title, body=body)
    _send_to_user(user_id, tag, notification=notification, data=data, tokens=tokens)


async def send_subscription_paid_personalized_notification(user_id: str, data: dict = None):
    """Send a personalized notification to all user's devices when unlimited subscription is purchased"""
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

    send_notification(user_id, "omi", body, data)


async def send_credit_limit_notification(user_id: str):
    """Send a personalized credit limit notification if not sent recently"""
    # Check if notification was sent recently (within 6 hours)
    if has_credit_limit_notification_been_sent(user_id):
        print(f"Credit limit notification already sent recently for user {user_id}")
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
    send_notification(user_id, title, body)

    # Cache that notification was sent (6 hours TTL)
    set_credit_limit_notification_sent(user_id)
    print(f"Credit limit notification sent to user {user_id}")


async def send_silent_user_notification(user_id: str):
    """Send a notification if a basic-plan user is silent for too long."""
    # Check if notification was sent recently (within 24 hours)
    if has_silent_user_notification_been_sent(user_id):
        print(f"Silent user notification already sent recently for user {user_id}")
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
    send_notification(user_id, title, body)

    # Cache that notification was sent (24 hours TTL)
    set_silent_user_notification_sent(user_id)
    print(f"Silent user notification sent to user {user_id}")


def send_training_data_submitted_notification(user_id: str):
    """Send a notification when user submits their training data opt-in request."""
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

    title = "omi"
    body = f"Hey {name}! Thanks for your interest in our training data program. We've received your request and our team will review it shortly. We'll notify you as soon as it's approved!"

    send_notification(user_id, title, body)
    print(f"Training data submitted notification sent to user {user_id}")


async def send_bulk_notification(user_tokens: list, title: str, body: str):
    """Send notification to multiple users in batches."""
    try:
        batch_size = 500
        num_batches = math.ceil(len(user_tokens) / batch_size)
        tag = _generate_tag(f"bulk:{title}:{body}")
        notification = messaging.Notification(title=title, body=body)

        def send_batch(batch_tokens):
            messages = [_build_message(token, tag, notification=notification) for token in batch_tokens]
            response = messaging.send_each(messages)

            # Collect permanently invalid tokens
            invalid_tokens = []
            for idx, result in enumerate(response.responses):
                if not result.success and result.exception:
                    error_code = getattr(result.exception, 'code', None)
                    if error_code in PERMANENT_FAILURE_CODES:
                        invalid_tokens.append(batch_tokens[idx])
                        print(f"Invalid token found - Error: {error_code}")

            return response, invalid_tokens

        tasks = [
            asyncio.to_thread(send_batch, user_tokens[i * batch_size : (i + 1) * batch_size])
            for i in range(num_batches)
        ]
        results = await asyncio.gather(*tasks)

        # Remove invalid tokens
        invalid_tokens = [token for _, batch_invalid in results for token in batch_invalid]
        if invalid_tokens:
            print(f"Removing {len(invalid_tokens)} invalid tokens")
            notification_db.remove_bulk_tokens(invalid_tokens)

    except Exception as e:
        print("Error sending bulk notification:", e)


def send_app_review_reply_notification(
    reviewer_uid: str, app_owner_uid: str, reply_body: str, app_id: str, app_name: str
):
    """Sends a notification to a user when their app review receives a reply."""
    app_owner = get_user_from_uid(app_owner_uid)
    owner_name = app_owner.get('display_name', 'The developer') if app_owner else 'The developer'
    title = f'{owner_name} ({app_name})'
    body = reply_body
    data = {'app_id': app_id, 'type': 'app_review_reply', 'navigate_to': f'/apps/{app_id}'}
    send_notification(reviewer_uid, title, body, data)


def send_new_app_review_notification(
    app_owner_uid: str, reviewer_uid: str, app_id: str, app_name: str, review_body: str
):
    """Sends a notification to the app owner when a new review is submitted."""
    reviewer = get_user_from_uid(reviewer_uid)
    reviewer_name = reviewer.get('display_name', 'A user') if reviewer else 'A user'
    title = f'{reviewer_name} reviewed {app_name}'
    body = review_body
    data = {'app_id': app_id, 'type': 'new_app_review', 'navigate_to': f'/apps/{app_id}'}
    send_notification(app_owner_uid, title, body, data)


def send_action_item_data_message(user_id: str, action_item_id: str, description: str, due_at: str):
    """
    Sends a data-only FCM message for action item reminder scheduling.
    The app receives this in the background and schedules a local notification.
    """
    print(f'send_action_item_data_message to user {user_id}')
    data = {
        'type': 'action_item_reminder',
        'action_item_id': action_item_id,
        'description': description,
        'due_at': due_at,
    }
    tag = _generate_tag(f"{user_id}:action_item_reminder:{action_item_id}")
    _send_to_user(user_id, tag, data=data, is_background=True, priority='high')


def send_merge_completed_message(user_id: str, merged_conversation_id: str, removed_conversation_ids: list):
    """
    Sends a data-only FCM message when conversation merge completes.

    The app receives this and:
    - Foreground: Shows toast "Conversations merged successfully"
    - Background: Shows local notification

    Args:
        user_id: The user's Firebase UID
        merged_conversation_id: ID of the primary (merged) conversation
        removed_conversation_ids: List of secondary conversation IDs that were removed
    """
    print(f'send_merge_completed_message to user {user_id}')
    data = {
        'type': 'merge_completed',
        'merged_conversation_id': merged_conversation_id,
        'removed_conversation_ids': ','.join(removed_conversation_ids),
    }
    tag = _generate_tag(f"{user_id}:merge_completed:{merged_conversation_id}")
    _send_to_user(user_id, tag, data=data, is_background=True, priority='high')


def send_important_conversation_message(user_id: str, conversation_id: str):
    """
    Sends a data-only FCM message when a long conversation (>30 min) completes.

    The app receives this and:
    - Shows a local notification: "You just had an important convo, click to share summary"
    - On tap: navigates to conversation detail with share sheet auto-open

    Args:
        user_id: The user's Firebase UID
        conversation_id: ID of the completed conversation
    """
    tokens = notification_db.get_all_tokens(user_id)
    if not tokens:
        print(f"No notification tokens found for user {user_id} for important conversation notification")
        return

    # FCM data values must be strings
    data = {
        'type': 'important_conversation',
        'conversation_id': conversation_id,
        'navigate_to': f'/conversation/{conversation_id}?share=1',
    }

    tag = _generate_tag(f'{user_id}:important_conversation:{conversation_id}')
    _send_to_user(user_id, tag, data=data, is_background=True, priority='high')


def send_action_item_update_message(user_id: str, action_item_id: str, description: str, due_at: str):
    """
    Sends a data-only FCM message when an action item is updated.
    The app receives this and reschedules the local notification.
    """
    print(f'send_action_item_update_message to user {user_id}')
    data = {
        'type': 'action_item_update',
        'action_item_id': action_item_id,
        'description': description,
        'due_at': due_at,
    }
    tag = _generate_tag(f"{user_id}:action_item_update:{action_item_id}")
    _send_to_user(user_id, tag, data=data, is_background=True, priority='high')


def send_action_item_deletion_message(user_id: str, action_item_id: str):
    """
    Sends a data-only FCM message when an action item is deleted.
    The app receives this and cancels the scheduled local notification.
    """
    print(f'send_action_item_deletion_message to user {user_id}')
    data = {
        'type': 'action_item_delete',
        'action_item_id': action_item_id,
    }
    tag = _generate_tag(f"{user_id}:action_item_delete:{action_item_id}")
    _send_to_user(user_id, tag, data=data, is_background=True, priority='high')


def send_action_item_created_notification(user_id: str, action_item_description: str):
    """
    Sends a notification when a new action item is created via the agentic chat.
    This provides confirmation that the task was successfully added.
    """
    # Truncate description if too long
    max_length = 60
    display_description = (
        action_item_description[:max_length] + '...'
        if len(action_item_description) > max_length
        else action_item_description
    )

    title = "Task Added"
    body = display_description

    send_notification(user_id, title, body)
    print(f"Action item created notification sent to user {user_id}")


def send_action_item_completed_notification(user_id: str, action_item_description: str):
    """
    Sends a notification when a user completes an action item via the agentic chat.
    This provides positive feedback and confirmation of task completion.
    """
    # Truncate description if too long
    max_length = 60
    display_description = (
        action_item_description[:max_length] + '...'
        if len(action_item_description) > max_length
        else action_item_description
    )

    title = "Task Complete! 🎉"
    body = display_description

    send_notification(user_id, title, body)
    print(f"Action item completed notification sent to user {user_id}")
