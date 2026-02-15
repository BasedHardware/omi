# Google Calendar Omi Integration

Manage your Google Calendar through Omi chat - create events, view your schedule, and more.

## Features

- **List Events** - View upcoming calendar events
- **Create Events** - Schedule meetings and appointments with natural language
- **Update Events** - Reschedule or modify existing events
- **Delete Events** - Remove events from your calendar
- **List Calendars** - See all your available calendars

## Setup

### 1. Create Google Cloud Project & OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google Calendar API**:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Calendar API"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Application type: **Web application**
   - Name: "Omi Google Calendar"
   - Authorized redirect URIs: Add your callback URL (see below)
5. Copy the **Client ID** and **Client Secret**

### 2. Deploy to Railway

1. Create a new project on [Railway](https://railway.app/)
2. Connect your GitHub repo or deploy from this folder
3. Add a **Redis** service to your project
4. Set environment variables:

```
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=https://your-app.up.railway.app/auth/google/callback
```

5. Deploy! Railway will automatically:
   - Install dependencies from `requirements.txt`
   - Start the server using `railway.toml` config
   - Provide `PORT` and `REDIS_URL` environment variables

### 3. Update Google OAuth Redirect URI

After deployment, update your Google OAuth credentials with the actual Railway URL:

```
https://your-app.up.railway.app/auth/google/callback
```

## Omi App Configuration

When creating/updating the Omi app, use these URLs:

| Field | Value |
|-------|-------|
| **Setup URL** | `https://your-app.up.railway.app/?uid={{uid}}` |
| **Setup Completed URL** | `https://your-app.up.railway.app/setup/google?uid={{uid}}` |
| **Chat Tools Manifest URL** | `https://your-app.up.railway.app/.well-known/omi-tools.json` |

## API Endpoints

### Chat Tools (POST)

| Endpoint | Description |
|----------|-------------|
| `/tools/list_events` | List upcoming calendar events |
| `/tools/create_event` | Create a new event |
| `/tools/get_event` | Get event details |
| `/tools/update_event` | Update an event |
| `/tools/delete_event` | Delete an event |
| `/tools/list_calendars` | List all calendars |

### OAuth & Setup (GET)

| Endpoint | Description |
|----------|-------------|
| `/` | Home page / setup UI |
| `/auth/google?uid=<uid>` | Start OAuth flow |
| `/auth/google/callback` | OAuth callback |
| `/setup/google?uid=<uid>` | Check setup status |
| `/disconnect?uid=<uid>` | Disconnect account |
| `/health` | Health check |
| `/.well-known/omi-tools.json` | Chat tools manifest |

## Local Development

1. Copy `.env.example` to `.env` and fill in your credentials
2. Set `GOOGLE_REDIRECT_URI=http://localhost:8080/auth/google/callback`
3. Add this to your Google OAuth redirect URIs
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python main.py`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID | Yes |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret | Yes |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL | Yes |
| `PORT` | Server port (default: 8080) | No |
| `REDIS_URL` | Redis connection URL | No (uses file storage if not set) |

## Example Chat Commands

- "What's on my calendar today?"
- "Show me my schedule for next week"
- "Create a meeting with John tomorrow at 2pm"
- "Schedule a dentist appointment on Friday at 10am"
- "Delete my 3pm meeting"
- "Reschedule my team sync to 4pm"
