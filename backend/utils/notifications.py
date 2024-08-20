from firebase_admin import messaging

def send_notification(token: str, title: str, body: str, data: dict = None):
    print('send_notification', token, title, body, data)
    notification = messaging.Notification(title=title, body=body)
    message = messaging.Message(notification=notification, token=token)

    if data:
        message.data = data

    try:
        response = messaging.send(message)
        print("Successfully sent message:", response)
    except Exception as e:
        print("Error sending message:", e)
