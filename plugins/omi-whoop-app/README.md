# Whoop Omi Integration

Track your recovery, strain, sleep, and workouts from your Whoop through Omi chat.

## Features

- **Recovery Score** - Check your daily recovery and HRV
- **Strain Score** - View your daily strain level
- **Sleep Data** - See sleep duration, stages, and quality
- **Workouts** - Review your recent training sessions
- **Weekly Summary** - Get trends and averages
- **Body Measurements** - View height, weight, max HR
- **Profile** - Access your Whoop profile info

## Setup

### 1. Create Whoop Developer App

1. Go to [Whoop Developer Portal](https://developer.whoop.com/)
2. Create a new application
3. Fill in application details:
   - Name: "Omi Integration"
   - Description: Your app description
   - Redirect URI: Add your callback URL (see below)
4. Request the following scopes:
   - `read:recovery`
   - `read:cycles`
   - `read:sleep`
   - `read:workout`
   - `read:profile`
   - `read:body_measurement`
   - `offline`
5. Copy the **Client ID** and **Client Secret**

### 2. Deploy to Railway

1. Create a new project on [Railway](https://railway.app/)
2. Connect your GitHub repo or deploy from this folder
3. Add a **Redis** service to your project
4. Set environment variables:

```
WHOOP_CLIENT_ID=your_client_id
WHOOP_CLIENT_SECRET=your_client_secret
WHOOP_REDIRECT_URI=https://your-app.up.railway.app/auth/whoop/callback
```

5. Deploy! Railway will automatically:
   - Install dependencies from `requirements.txt`
   - Start the server using `railway.toml` config
   - Provide `PORT` and `REDIS_URL` environment variables

### 3. Update Whoop OAuth Redirect URI

After deployment, update your Whoop app's redirect URI:

```
https://your-app.up.railway.app/auth/whoop/callback
```

## Omi App Configuration

When creating/updating the Omi app, use these URLs:

| Field | Value |
|-------|-------|
| **Setup URL** | `https://your-app.up.railway.app/?uid={{uid}}` |
| **Setup Completed URL** | `https://your-app.up.railway.app/setup/whoop?uid={{uid}}` |
| **Chat Tools Manifest URL** | `https://your-app.up.railway.app/.well-known/omi-tools.json` |

## API Endpoints

### Chat Tools (POST)

| Endpoint | Description |
|----------|-------------|
| `/tools/get_recovery` | Get recovery score and HRV |
| `/tools/get_strain` | Get daily strain score |
| `/tools/get_sleep` | Get sleep data |
| `/tools/get_workouts` | Get recent workouts |
| `/tools/get_weekly_summary` | Get weekly averages |
| `/tools/get_body_measurements` | Get body measurements |
| `/tools/get_profile` | Get user profile |

### OAuth & Setup (GET)

| Endpoint | Description |
|----------|-------------|
| `/` | Home page / setup UI |
| `/auth/whoop?uid=<uid>` | Start OAuth flow |
| `/auth/whoop/callback` | OAuth callback |
| `/setup/whoop?uid=<uid>` | Check setup status |
| `/disconnect?uid=<uid>` | Disconnect account |
| `/health` | Health check |
| `/.well-known/omi-tools.json` | Chat tools manifest |

## Local Development

1. Copy `.env.example` to `.env` and fill in your credentials
2. Set `WHOOP_REDIRECT_URI=http://localhost:8080/auth/whoop/callback`
3. Add this to your Whoop app's redirect URIs
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python main.py`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `WHOOP_CLIENT_ID` | Whoop OAuth Client ID | Yes |
| `WHOOP_CLIENT_SECRET` | Whoop OAuth Client Secret | Yes |
| `WHOOP_REDIRECT_URI` | OAuth callback URL | Yes |
| `PORT` | Server port (default: 8080) | No |
| `REDIS_URL` | Redis connection URL | No (uses file storage if not set) |

## Example Chat Commands

- "What's my recovery today?"
- "How did I sleep last night?"
- "What's my strain level?"
- "Show my recent workouts"
- "Give me my weekly summary"
- "What's my HRV?"

## Understanding Whoop Metrics

### Recovery Score (0-100%)
- **Green (67-100%)**: High recovery, ready for strain
- **Yellow (34-66%)**: Moderate recovery, proceed with caution
- **Red (0-33%)**: Low recovery, prioritize rest

### Strain Score (0-21)
- **0-9**: Light day
- **10-13**: Moderate strain
- **14-17**: High strain
- **18-21**: Overreaching (very high)

### Key Metrics
- **HRV (Heart Rate Variability)**: Higher is generally better
- **RHR (Resting Heart Rate)**: Lower is generally better
- **Sleep Performance**: How well you met your sleep need
- **Sleep Efficiency**: Time asleep vs time in bed
