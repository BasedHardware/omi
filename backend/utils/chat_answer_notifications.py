"""Client-displayed FCM helpers for click-to-talk / chat-answer notifications (#4375)."""

import hashlib
import logging

from firebase_admin import messaging

import database.notifications as notification_db

logger = logging.getLogger(__name__)

IOS_BUNDLE_ID = 'com.friend-app-with-wearable.ios12'
PERMANENT_FAILURE_CODES = frozenset(
    ['UNREGISTERED', 'INVALID_REGISTRATION_TOKEN', 'NOT_FOUND']
)


def _generate_tag(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()[:16]


def _stringify_fcm_data(data):
    if not data:
        return {}
    return {str(k): '' if v is None else str(v) for k, v in data.items()}


def _build_client_displayed_message(token, tag, title, body, data, priority='high'):
    """FCM message Flutter renders locally with BigText on Android (#4375)."""
    link = data.get('navigate_to')
    webpush_kwargs = {
        'headers': {'Topic': tag, 'Urgency': 'high'},
        'notification': messaging.WebpushNotification(title=title, body=body, icon='/logo.png'),
    }
    if link and str(link).startswith('https://'):
        webpush_kwargs['fcm_options'] = messaging.WebpushFCMOptions(link=link)

    return messaging.Message(
        token=token,
        notification=None,
        data=data,
        android=messaging.AndroidConfig(collapse_key=tag, priority=priority),
        apns=messaging.APNSConfig(
            headers={
                'apns-collapse-id': tag,
                'apns-priority': '10',
                'apns-push-type': 'alert',
                'apns-topic': IOS_BUNDLE_ID,
            },
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(title=title, body=body),
                    sound='default',
                ),
            ),
        ),
        webpush=messaging.WebpushConfig(**webpush_kwargs),
    )


def send_client_displayed_notification(user_id, title, body, data=None, tokens=None):
    """Send a chat/plugin answer push that Flutter renders with BigText (#4375)."""
    logger.info(f'send_client_displayed_notification to user {user_id}')
    payload = _stringify_fcm_data(data)
    payload['push_type'] = 'chat_answer'
    payload['title'] = title
    payload['body'] = body
    tag = _generate_tag(f"{user_id}:{title}:{body}:{payload.get('id', '')}")
    if tokens is None:
        tokens = notification_db.get_all_tokens(user_id)
    if not tokens:
        logger.info(f"No tokens found for user {user_id}")
        return
    messages = [_build_client_displayed_message(token, tag, title, body, payload) for token in tokens]
    try:
        response = messaging.send_each(messages)
        invalid_tokens = []
        success_count = 0
        for idx, result in enumerate(response.responses):
            if result.success:
                success_count += 1
            elif result.exception:
                error_code = getattr(result.exception, 'code', None)
                if error_code in PERMANENT_FAILURE_CODES:
                    invalid_tokens.append(tokens[idx])
        if invalid_tokens:
            notification_db.remove_bulk_tokens(invalid_tokens)
        logger.info(f'FCM client-displayed batch send: {success_count}/{len(tokens)} successful')
    except Exception as e:
        logger.error(f'FCM client-displayed batch send error: {e}')
