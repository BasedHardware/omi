# Proactive Notifications Documentation

## Overview
Proactive notifications in Omi are push notifications that are sent to users based on specific triggers or events, even when the app is not actively in use. These notifications are handled through Firebase Cloud Messaging (FCM) and Awesome Notifications for local handling.

## Implementation Details

### 1. Setup and Initialization
The notification system is initialized in the `NotificationService` class:
```dart
NotificationService.instance.initialize()
```

### 2. Token Management
- When a user logs in, their FCM token is automatically saved to the backend
- The token is used to send targeted notifications to specific users
- Tokens are refreshed automatically when needed

### 3. Types of Proactive Notifications

#### a. System Notifications
- Updates about system status
- Important announcements
- Service updates

#### b. User-triggered Notifications
- Responses to user actions
- Scheduled reminders
- Activity updates

### 4. Sending Notifications

#### Backend API Endpoint
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

### 5. Handling Notifications

#### In-App Handling
Notifications are handled by the `NotificationUtil` class which manages:
- Notification actions
- Deep linking
- Background/foreground notification display

#### Background Handling
The app can receive and process notifications even when in the background using:
- `NotificationOnKillService` for Android
- `NotificationService` for iOS

## Best Practices
1. Always include relevant context in notification payload
2. Use appropriate notification channels
3. Handle both foreground and background states
4. Implement proper error handling

## Testing
To test proactive notifications:
1. Ensure FCM is properly configured
2. Verify token registration
3. Test notifications in various app states (foreground, background, terminated)

## Troubleshooting
- Verify FCM token is properly registered
- Check notification permissions
- Ensure proper configuration in Firebase Console
- Verify backend secret key for authentication
