# Hive Integration for Omi

Manage your Hive projects with voice commands through your Omi device. Create tasks, view projects, track actions, and search – all hands-free!

---

## Features

- **View Projects** - See all your Hive projects at a glance
- **Create Tasks** - Add tasks to projects with voice
- **Manage Actions** - Create and track action items
- **Search Everything** - Find tasks and projects instantly
- **Secure API Key** - Your credentials are stored securely

---

## Quick Start

1. Install the Hive app from the Omi App Store
2. Click "Connect Hive" and enter your API key
3. (Optional) Set a default project for quick task creation
4. Start using voice commands!

---

## Getting Your API Key

1. Log into your Hive account at [app.hive.com](https://app.hive.com)
2. Click your profile icon in the top right corner
3. Select "Edit Profile"
4. Click on the "API Info" tab
5. Generate or copy your existing API key

> **Note:** Hive uses API key authentication (not OAuth). Your API key is stored securely and only used to make requests to Hive's API on your behalf.

---

## Voice Commands

| Command | Description |
| ------- | ----------- |
| "Show my projects" | List all your Hive projects |
| "Create a task called Review proposal" | Create a new task |
| "Create a task in Marketing project" | Create a task in a specific project |
| "Show tasks in the Website project" | View tasks in a project |
| "Add an action to follow up with client" | Create an action item |
| "Search for tasks about budget" | Search across all tasks |

---

## Omi App Store Details

### App Information

| Field | Value |
| ----- | ----- |
| **App Name** | Hive |
| **Category** | Productivity & Organization |
| **Description** | Manage your Hive projects with voice commands. Create tasks, view projects, track actions, and search – all hands-free through your Omi device. |
| **Author** | Omi Community |
| **Version** | 1.0.0 |

### Capabilities

- ✅ **External Integration** (required for chat tools)
- ✅ **Chat** (for voice command responses)

### URLs

| URL Type | URL |
| -------- | --- |
| **App Home URL** | `https://YOUR-HIVE-APP.up.railway.app/` |
| **Setup Completed URL** | `https://YOUR-HIVE-APP.up.railway.app/setup/hive` |
| **Chat Tools Manifest URL** | `https://YOUR-HIVE-APP.up.railway.app/.well-known/omi-tools.json` |

> **Important:** Omi automatically appends `?uid=USER_ID` to these URLs. Do NOT include `{uid}` in the URL.

---

## Chat Tools

This app exposes a manifest endpoint at `/.well-known/omi-tools.json` that Omi automatically fetches when the app is created or updated.

### Available Tools

| Tool | Description |
| ---- | ----------- |
| `get_projects` | Get the user's Hive projects |
| `get_tasks` | Get tasks from a Hive project |
| `create_task` | Create a new task in Hive |
| `create_action` | Create an action item |
| `search` | Search tasks and projects |

---

## Development

### Prerequisites

- Python 3.8+
- Hive account with API access

### Local Setup

```bash
# Navigate to the plugin directory
cd plugins/hive

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file (optional for local dev)
cp .env.example .env

# Run the server
python main.py
```

The server will start at `http://localhost:8080`.

### Environment Variables

```env
# Server Configuration
PORT=8080

# Redis (optional - for production use)
# If not set, the app will use file-based storage
REDIS_URL=
REDIS_PRIVATE_URL=
```

---

## Deploy to Railway

### Step 1: Create Railway Project

1. Go to [Railway](https://railway.app) and sign in
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository and choose the `plugins/hive` folder

### Step 2: Add Redis Database (Optional but Recommended)

1. In your Railway project, click **"+ New"** → **"Database"** → **"Add Redis"**
2. Railway automatically creates and connects the Redis instance
3. The `REDIS_URL` environment variable is set automatically

### Step 3: Configure Root Directory

If deploying from the main repo, set the **Root Directory** to `plugins/hive`:

1. Go to **Settings** → **Build** → **Root Directory**
2. Enter: `plugins/hive`

### Step 4: Update Omi App Store

Update your app URLs in the Omi App Store:

| URL Type | Value |
| -------- | ----- |
| **App Home URL** | `https://YOUR-APP.up.railway.app/` |
| **Setup Completed URL** | `https://YOUR-APP.up.railway.app/setup/hive` |
| **Chat Tools Manifest URL** | `https://YOUR-APP.up.railway.app/.well-known/omi-tools.json` |

### Railway Architecture

```
┌─────────────────────────────────────────────────┐
│                 Railway Project                  │
├─────────────────────────────────────────────────┤
│  ┌───────────────┐     ┌───────────────────┐   │
│  │   Hive App    │────▶│  Redis Database   │   │
│  │   (FastAPI)   │     │  (Persistent)     │   │
│  │               │     │                   │   │
│  │  - API key    │     │  - User keys      │   │
│  │  - Chat tools │     │  - Settings       │   │
│  │  - GraphQL    │     │  - Preferences    │   │
│  └───────────────┘     └───────────────────┘   │
│         │                                       │
│         ▼                                       │
│  https://YOUR-APP.up.railway.app               │
└─────────────────────────────────────────────────┘
```

---

## API Endpoints

| Endpoint | Method | Description |
| -------- | ------ | ----------- |
| `/` | GET | Home page / App settings |
| `/health` | GET | Health check |
| `/settings/api-key` | POST | Connect API key |
| `/setup/hive` | GET | Check setup status |
| `/disconnect` | GET | Disconnect account |
| `/tools/get_projects` | POST | Chat tool: Get projects |
| `/tools/get_tasks` | POST | Chat tool: Get tasks |
| `/tools/create_task` | POST | Chat tool: Create task |
| `/tools/create_action` | POST | Chat tool: Create action |
| `/tools/search` | POST | Chat tool: Search |
| `/.well-known/omi-tools.json` | GET | Chat tools manifest |

---

## Troubleshooting

### "User not connected"

- Make sure you've entered your API key in the app settings
- Verify your API key is correct by testing it in Hive

### "Could not find project"

- Check the project name pronunciation
- Try setting a default project in app settings
- Use "Show my projects" to see available projects

### "Failed to create task"

- Ensure you have permission to create tasks in the project
- Try specifying a different project

### API key not working

- Make sure you copied the entire API key
- Check that your Hive account has API access enabled
- Try generating a new API key in Hive

---

## Hive API Reference

This integration uses Hive's GraphQL API:

- **Endpoint:** `https://prod-gql.hive.com/graphql`
- **Authentication:** API key passed in `api_key` header
- **Documentation:** [developers.hive.com](https://developers.hive.com)

---

## License

MIT License - feel free to modify and distribute.

---

## Support

For issues or feature requests, please open an issue on GitHub or contact the Omi community.

---

Made with ❤️ for Omi


