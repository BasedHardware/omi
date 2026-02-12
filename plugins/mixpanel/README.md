# Omi Mixpanel Analytics Plugin

Chat tools for exploring Mixpanel analytics data from Omi chat.

## Chat Tools

| Tool | What it does |
|------|-------------|
| `query_events` | Count events over a time range |
| `segmentation` | Break down an event by a property |
| `funnel_analysis` | Analyze conversion through a sequence of events |
| `retention` | Analyze user return rates after an initial event |
| `query_profiles` | Search user profiles by property filters |
| `top_events` | Get the most popular events |

## Setup

### 1. Prerequisites

- A Mixpanel account with a **Service Account** (create one under Organization Settings > Service Accounts)
- Python 3.10+

### 2. Install dependencies

```bash
cd plugins/mixpanel
pip install -r requirements.txt
```

### 3. Run locally

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Expose via ngrok

```bash
ngrok http 8000
```

Copy the ngrok HTTPS URL (e.g. `https://abc123.ngrok-free.app`).

### 5. Register in Omi App Store

Create a new app with:
- **App Home URL**: your ngrok URL
- **Chat Tools Manifest URL**: `<ngrok-url>/.well-known/omi-tools.json`

### 6. Connect Mixpanel

Open the app's setup page (the App Home URL with `?uid=YOUR_UID`), enter your:
- **Project ID** (from Mixpanel project settings)
- **Service Account Username**
- **Service Account Secret**

### 7. Use in Omi chat

Ask questions like:
- "What are the top events this week?"
- "Show me sign ups by country for the last 7 days"
- "What's the conversion rate from Sign Up to Purchase?"
- "What's the retention for users who signed up?"

## Deploy to Railway

```bash
railway init
railway up
```

Set `REDIS_URL` in your Railway environment variables for persistent storage.
