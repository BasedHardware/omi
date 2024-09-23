import asyncio
import math

from firebase_admin import messaging

import database.notifications as notification_db


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


async def send_bulk_notification(user_tokens: list, title: str, body: str):
    try:
        batch_size = 500
        num_batches = math.ceil(len(user_tokens) / batch_size)

        def send_batch(batch_users):
            messages = [
                messaging.Message(
                    notification=messaging.Notification(title=title, body=body),
                    token=token
                ) for token in batch_users
            ]
            return messaging.send_all(messages)

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
