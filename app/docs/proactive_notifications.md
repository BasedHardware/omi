# Proactive Notifications

Omi uses a robust notification system to keep users informed and engaged, even when the app isn't actively running. This guide explains how to implement and use proactive notifications in your Omi app development.

## 📱 Quick Implementation

```dart
// Initialize notifications
await NotificationService.instance.initialize();

// Send a notification
await sendNotification({
    'uid': 'user_id',
    'title': 'Hello',
    'body': 'This is a test notification'
});
```

## 🔧 System Components

### 🔐 Authentication & Setup

1. **Initialize the Service**
   ```dart
   await NotificationService.instance.initialize()
   ```

2. **Token Management**
   - Automatic FCM token registration on login
   - Secure token storage in backend
   - Automatic token refresh handling

### 📬 Notification Types

1. **System Notifications**
   - System status updates
   - Important announcements
   - Service updates

2. **User Notifications**
   - Action responses
   - Scheduled reminders
   - Activity updates

## 🔌 API Integration

### Send Notification
```http
POST /v1/notification
Headers: 
  - secret_key: [ADMIN_KEY]
Body:
{
    "uid": "user_id",
    "title": "Notification Title",
    "body": "Notification Message",
    "data": {} // Optional additional data
}
```

## 🛠 Implementation Guide

### In-App Handling
```dart
class NotificationUtil {
  // Handle notification actions
  static Future<void> onActionReceivedMethod(
    ReceivedAction receivedAction
  ) async {
    // Your handling logic
  }
}
```

### Background Processing
- Android: `NotificationOnKillService`
- iOS: `NotificationService`

## ✅ Best Practices

1. **Payload Structure**
   - Include necessary context
   - Keep payload size minimal
   - Use appropriate channels

2. **State Handling**
   - Handle foreground state
   - Manage background state
   - Process terminated state

## 🔍 Troubleshooting

### Common Issues
- FCM token not registered
- Missing notification permissions
- Firebase Console misconfiguration
- Invalid backend secret key

### Quick Fixes
1. Verify Firebase setup in console
2. Check app notification permissions
3. Validate backend configuration
4. Test in different app states

## 💬 Need Help?

- Join our [Discord Community](http://discord.omi.me)
- Check [Firebase Documentation](https://firebase.google.com/docs/cloud-messaging)
- Visit [Omi Docs](https://docs.omi.me/)
