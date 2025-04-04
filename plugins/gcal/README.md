# OMI Google Calendar Integration

This plugin allows you to import your Google Calendar events into OMI as facts, enabling OMI to be aware of your schedule and provide context-aware assistance.

## Features

- OAuth authentication with Google Calendar API
- Select which calendar to import from
- Choose how far back to import events
- Import events as facts into OMI

## Setup

### Prerequisites

1. Python 3.6 or higher
2. Flask
3. Google API client libraries

### Installation

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Configure your environment variables in the `.env` file:

```
GOOGLE_CALENDAR_CLIENT_ID=your_client_id
GOOGLE_CALENDAR_CLIENT_SECRET=your_client_secret
GOOGLE_CALENDAR_REDIRECT_URI=your_redirect_uri
GOOGLE_CALENDAR_AUTH_URL=https://accounts.google.com/o/oauth2/auth
```

3. Update the `app.py` file with your OMI App ID and API Key:

```python
APP_ID = "your_omi_app_id"
API_KEY = "your_omi_api_key"
```

### Running the Plugin

1. Start the Flask application:

```bash
python app.py
```

2. Open your browser and navigate to `http://localhost:5001?uid=your_omi_user_id`

## How to Use

1. Click the "Connect Google Calendar" button
2. Authorize OMI to access your Google Calendar
3. Select which calendar you want to import events from
4. Choose how many days back you want to import events from
5. Click "Import Events"

## Technical Details

- The plugin uses OAuth 2.0 for authentication with Google Calendar API
- Events are fetched from the selected calendar and formatted as facts
- Facts are submitted to the OMI API using the provided App ID and API Key
- The plugin uses Flask for the web interface and API endpoints

## Troubleshooting

- If you encounter port conflicts, you can change the port in `app.py` by modifying the line: `app.run(host='0.0.0.0', port=5001, debug=True)`
- If authentication fails, check that your Google Calendar API credentials are correct in the `.env` file
- If events are not being imported, check that your OMI App ID and API Key are correct in `app.py`