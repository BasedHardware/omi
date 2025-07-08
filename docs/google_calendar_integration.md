# Google Calendar Integration for Omi

The Google Calendar integration allows users to automatically create calendar events from their conversations captured by Omi. This integration provides seamless synchronization between your conversations and Google Calendar.

## Features

- **Automatic Event Creation**: Automatically creates calendar events when conversations are processed
- **OAuth2 Authentication**: Secure authentication using Google's OAuth2 flow
- **Configurable Settings**: Users can customize event creation behavior
- **Event Management**: View, create, and manage calendar events through the API
- **Real-time Synchronization**: Events are created in real-time as conversations are processed

## Setup Instructions

### 1. Prerequisites

- Google Cloud Project with Calendar API enabled
- OAuth2 credentials configured
- Required Python packages installed

### 2. Environment Variables

Set the following environment variables:

```bash
export GOOGLE_CLIENT_ID="your_google_client_id"
export GOOGLE_CLIENT_SECRET="your_google_client_secret"
export GOOGLE_REDIRECT_URI="http://localhost:8000/v1/calendar/oauth/callback"
```

### 3. Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Calendar API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Calendar API"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client ID"
   - Choose "Web application"
   - Add authorized redirect URI: `http://localhost:8000/v1/calendar/oauth/callback`
   - Save the Client ID and Client Secret

### 4. Required OAuth Scopes

The integration requires the following OAuth scopes:
- `https://www.googleapis.com/auth/calendar`
- `https://www.googleapis.com/auth/userinfo.email`
- `https://www.googleapis.com/auth/userinfo.profile`

### 5. Installation

Run the setup script to install dependencies and check configuration:

```bash
python backend/setup_google_calendar.py
```

## API Endpoints

### Authentication
- `GET /v1/calendar/auth` - Initiate OAuth flow
- `GET /v1/calendar/oauth/callback` - Handle OAuth callback

### Status and Configuration
- `GET /v1/calendar/status` - Check integration status
- `GET /v1/calendar/config` - Get user configuration
- `PUT /v1/calendar/config` - Update user configuration
- `DELETE /v1/calendar/disconnect` - Disconnect integration

### Event Management
- `POST /v1/calendar/events` - Create calendar event
- `GET /v1/calendar/events` - Get upcoming events
- `GET /v1/calendar/events/history` - Get event history

### Testing
- `GET /v1/calendar/test` - Test integration

## Configuration Options

Users can configure the following settings:

```json
{
  "auto_create_events": true,
  "event_duration_minutes": 60,
  "default_timezone": "UTC",
  "include_transcript": true,
  "include_summary": true,
  "calendar_id": "primary"
}
```

### Configuration Parameters

- **auto_create_events**: Enable/disable automatic event creation
- **event_duration_minutes**: Default duration for events (when end time is not available)
- **default_timezone**: Default timezone for events
- **include_transcript**: Include conversation transcript in event description
- **include_summary**: Include conversation summary in event description
- **calendar_id**: Target calendar ID (defaults to primary calendar)

## Usage Flow

### 1. User Authentication

```javascript
// Get OAuth URL
const response = await fetch('/v1/calendar/auth');
const data = await response.json();
window.location.href = data.auth_url;
```

### 2. Check Status

```javascript
const response = await fetch('/v1/calendar/status');
const status = await response.json();
console.log('Connected:', status.connected);
```

### 3. Create Event

```javascript
const eventData = {
  summary: "Team Meeting",
  description: "Weekly team sync",
  start_time: "2024-01-15T10:00:00Z",
  end_time: "2024-01-15T11:00:00Z",
  timezone: "UTC"
};

const response = await fetch('/v1/calendar/events', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(eventData)
});
```

### 4. Get Events

```javascript
const response = await fetch('/v1/calendar/events?days_ahead=7');
const data = await response.json();
console.log('Upcoming events:', data.events);
```

## Automatic Event Creation

When a conversation is processed, the system automatically:

1. Checks if the user has calendar integration enabled
2. Extracts relevant information from the conversation:
   - Title from structured data
   - Summary from conversation analysis
   - Start/end times from conversation timestamps
   - Transcript content
3. Creates a calendar event with the extracted information
4. Saves the event record to the database

### Event Content

Calendar events include:
- **Title**: "Omi: [Conversation Title]"
- **Description**: Combination of summary and transcript (based on user preferences)
- **Start Time**: Conversation start time
- **End Time**: Conversation end time or start time + default duration
- **Timezone**: User's configured timezone

## Database Schema

### calendar_integrations
```javascript
{
  uid: "user_id",
  access_token: "encrypted_token",
  refresh_token: "encrypted_refresh_token",
  token_expiry: "2024-01-15T12:00:00Z",
  calendar_id: "primary",
  calendar_name: "Primary Calendar",
  timezone: "America/New_York",
  preferences: {},
  created_at: "2024-01-15T10:00:00Z",
  updated_at: "2024-01-15T10:00:00Z"
}
```

### calendar_configs
```javascript
{
  auto_create_events: true,
  event_duration_minutes: 60,
  default_timezone: "UTC",
  include_transcript: true,
  include_summary: true,
  calendar_id: "primary"
}
```

### calendar_events
```javascript
{
  id: "event_id",
  uid: "user_id",
  summary: "Event Title",
  description: "Event description",
  start_time: "2024-01-15T10:00:00Z",
  end_time: "2024-01-15T11:00:00Z",
  calendar_id: "primary",
  event_id: "google_event_id",
  created_at: "2024-01-15T10:00:00Z",
  updated_at: "2024-01-15T10:00:00Z"
}
```

## Error Handling

The integration includes comprehensive error handling for:
- OAuth token expiration and refresh
- Google API rate limiting
- Network connectivity issues
- Invalid calendar permissions
- Database connection errors

## Security Considerations

- OAuth tokens are stored securely in Firestore
- Refresh tokens are used to maintain access without user re-authentication
- API calls are rate-limited to prevent abuse
- User data is only accessed with explicit consent

## Mobile App Integration

The Flutter app includes:
- Calendar integration setup page
- Configuration management
- Event viewing and creation
- Status monitoring

### Flutter Usage

```dart
import 'package:friend_private/backend/http/calendar.dart';
import 'package:friend_private/pages/calendar/calendar_integration_page.dart';

// Navigate to calendar integration page
Navigator.push(
  context,
  MaterialPageRoute(
    builder: (context) => CalendarIntegrationPage(),
  ),
);
```

## Testing

### Manual Testing

1. Run the test endpoint:
```bash
curl -X GET "http://localhost:8000/v1/calendar/test" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

2. Check integration status:
```bash
curl -X GET "http://localhost:8000/v1/calendar/status" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Automated Testing

Create a test conversation and verify that a calendar event is created:

```python
from utils.calendar import calendar_service
from models.calendar import CalendarEventCreate

# Test event creation
event_data = CalendarEventCreate(
    summary="Test Event",
    description="Test description",
    start_time=datetime.now(),
    end_time=datetime.now() + timedelta(hours=1)
)

result = calendar_service.create_event(uid, event_data)
print("Event created:", result)
```

## Troubleshooting

### Common Issues

1. **OAuth Token Expired**
   - Solution: Tokens are automatically refreshed
   - If refresh fails, user needs to re-authenticate

2. **Calendar API Quota Exceeded**
   - Solution: Implement exponential backoff
   - Check Google Cloud Console for quota limits

3. **Permission Denied**
   - Solution: Ensure correct OAuth scopes are configured
   - Check Google Cloud Console permissions

4. **Event Creation Failed**
   - Solution: Check calendar permissions
   - Verify event data format

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Monitoring

The integration includes monitoring for:
- Event creation success/failure rates
- API response times
- OAuth token refresh frequency
- User engagement metrics

## Future Enhancements

- Support for multiple calendars
- Calendar event updates and deletions
- Recurring event patterns
- Advanced event filtering
- Integration with other calendar providers

## Support

For support or questions about the Google Calendar integration:
- Check the logs for error messages
- Review the setup documentation
- Contact the development team
- Submit issues through the project repository