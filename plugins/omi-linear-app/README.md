# Linear Integration for Omi

Manage your Linear issues with voice commands through your Omi device. Create issues, track your work, update statuses, and add comments – all hands-free!

![Linear + Omi](https://linear.app/static/apple-touch-icon.png)

---

## 🚨 OMI APP STORE - COPY THESE URLs

**Current ngrok URL:** `https://spacious-undiscouragingly-kelle.ngrok-free.dev`

### App Store Form Fields

| Field | Value |
|-------|-------|
| **App Name** | Linear |
| **Category** | Productivity |
| **Description** | Manage your Linear issues with voice commands. Create issues, track work, update statuses, and add comments – all hands-free through your Omi device. |

### URLs to Enter in Omi App Store

| Field | URL |
|-------|-----|
| **App Home URL** | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/` |
| **Setup Completed URL** | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/setup/linear` |
| **Chat Tools Manifest URL** | `https://spacious-undiscouragingly-kelle.ngrok-free.dev/.well-known/omi-tools.json` |

### Linear OAuth Redirect URI (Add to Linear Dashboard)

```
https://spacious-undiscouragingly-kelle.ngrok-free.dev/auth/linear/callback
```

### Capabilities to Enable

- ✅ **External Integration** (required for chat tools)
- ✅ **Chat** (for voice command responses)

---

## 🎯 Features

- **➕ Create Issues** - Create new issues with title, description, and priority
- **📋 List My Issues** - See all issues assigned to you
- **🔄 Update Status** - Move issues through workflow states (Todo → In Progress → Done)
- **🔍 Search Issues** - Find issues by keyword or topic
- **📄 Get Issue Details** - View full details of any issue
- **💬 Add Comments** - Add comments and updates to issues

---

## 🚀 Quick Start

1. Install the Linear app from the Omi App Store
2. Click "Connect Linear" to authenticate with your workspace
3. (Optional) Set a default team for issue creation
4. Start using voice commands!

---

## 🗣️ Voice Commands

| Command                                      | Description                    |
| -------------------------------------------- | ------------------------------ |
| "Create an issue: Fix login bug"             | Create a new issue             |
| "Create urgent issue: Server is down"        | Create with priority           |
| "Show my issues"                             | List your assigned issues      |
| "Show my in-progress issues"                 | Filter by status               |
| "Move ENG-123 to Done"                       | Update issue status            |
| "Mark PROD-456 as In Progress"               | Start working on an issue      |
| "Search for authentication issues"           | Find issues by keyword         |
| "What's the status of ENG-789?"              | Get issue details              |
| "Tell me about PROD-123"                     | Get full issue information     |
| "Add comment to ENG-456: Fixed the bug"      | Add a comment to an issue      |

---

## 📋 Omi App Store Details

### App Information

| Field           | Value                                                                                              |
| --------------- | -------------------------------------------------------------------------------------------------- |
| **App Name**    | Linear                                                                                             |
| **Category**    | Productivity & Work                                                                                |
| **Description** | Manage your Linear issues with voice commands. Create issues, track work, update statuses, and add comments – all hands-free through your Omi device. |
| **Author**      | Omi Community                                                                                      |
| **Version**     | 1.0.0                                                                                              |

### Capabilities

- ✅ **External Integration** (required for chat tools)
- ✅ **Chat** (for voice command responses)

### URLs

| URL Type                    | URL                                                       |
| --------------------------- | --------------------------------------------------------- |
| **App Home URL**            | `https://YOUR-APP.up.railway.app/`                        |
| **Setup Completed URL**     | `https://YOUR-APP.up.railway.app/setup/linear`            |
| **Chat Tools Manifest URL** | `https://YOUR-APP.up.railway.app/.well-known/omi-tools.json` |

> **Important:** Omi automatically appends `?uid=USER_ID` to these URLs. Do NOT include `{uid}` in the URL.

---

## 🔧 Chat Tools

This app exposes a manifest endpoint at `/.well-known/omi-tools.json` that Omi automatically fetches when the app is created or updated.

### Available Tools

| Tool                 | Description                           |
| -------------------- | ------------------------------------- |
| `create_issue`       | Create a new issue in Linear          |
| `list_my_issues`     | List issues assigned to the user      |
| `update_issue_status`| Update an issue's workflow status     |
| `search_issues`      | Search for issues by text             |
| `get_issue`          | Get detailed info about an issue      |
| `add_comment`        | Add a comment to an existing issue    |

---

## 🔐 Linear Developer Setup

### Create OAuth Application

1. Go to [Linear Settings > API](https://linear.app/settings/api)
2. Click "Create OAuth application"
3. Fill in the details:
   - **Application name:** Omi Integration
   - **Developer name:** Your name
   - **Developer URL:** https://omi.me
   - **Redirect URI:** `https://YOUR-APP.up.railway.app/auth/linear/callback`
4. Note your **Client ID** and **Client Secret**

### Required Scopes

The app requests these Linear permissions:
- `read` - Read access to workspace data
- `write` - Write access to issues
- `issues:create` - Create new issues
- `comments:create` - Add comments to issues

---

## 🛠️ Development

### Prerequisites

- Python 3.8+
- Linear workspace with admin access

### Local Setup

```bash
# Navigate to the plugin directory
cd plugins/linear

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your credentials

# Run the server
python main.py
```

### Environment Variables

```env
LINEAR_CLIENT_ID=your_client_id
LINEAR_CLIENT_SECRET=your_client_secret
LINEAR_REDIRECT_URI=https://your-domain.com/auth/linear/callback
PORT=8080
REDIS_URL=  # Optional: for production use
```

### Local Testing with ngrok

```bash
# Start ngrok
ngrok http 8080

# Update LINEAR_REDIRECT_URI in .env with ngrok URL
# Update redirect URI in Linear OAuth app settings
```

---

## 🚀 Deploy to Railway

### Step 1: Create Railway Project

1. Go to [Railway](https://railway.app) and sign in
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select your repository and choose the `plugins/linear` folder

### Step 2: Add Redis Database

1. In your Railway project, click **"+ New"** → **"Database"** → **"Add Redis"**
2. Railway automatically creates and connects the Redis instance
3. The `REDIS_URL` environment variable is set automatically

### Step 3: Configure Environment Variables

Go to your service's **Variables** tab and add:

| Variable               | Value                                                |
| ---------------------- | ---------------------------------------------------- |
| `LINEAR_CLIENT_ID`     | Your Linear OAuth Client ID                          |
| `LINEAR_CLIENT_SECRET` | Your Linear OAuth Client Secret                      |
| `LINEAR_REDIRECT_URI`  | `https://YOUR-APP.up.railway.app/auth/linear/callback` |

> **Note:** Replace `YOUR-APP` with your actual Railway app domain (shown in Settings → Domains)

### Step 4: Configure Root Directory

If deploying from the main repo, set the **Root Directory** to `plugins/linear`:

1. Go to **Settings** → **Build** → **Root Directory**
2. Enter: `plugins/linear`

### Step 5: Update Linear OAuth App

Add your Railway URL as a redirect URI in your Linear OAuth application settings:

```
https://YOUR-APP.up.railway.app/auth/linear/callback
```

### Step 6: Update Omi App Store

Update your app URLs in the Omi App Store:

| URL Type                    | Value                                                    |
| --------------------------- | -------------------------------------------------------- |
| **App Home URL**            | `https://YOUR-APP.up.railway.app/`                       |
| **Setup Completed URL**     | `https://YOUR-APP.up.railway.app/setup/linear`           |
| **Chat Tools Manifest URL** | `https://YOUR-APP.up.railway.app/.well-known/omi-tools.json` |

### Railway Architecture

```
┌─────────────────────────────────────────────────┐
│                 Railway Project                  │
├─────────────────────────────────────────────────┤
│  ┌───────────────┐     ┌───────────────────┐   │
│  │  Linear App   │────▶│  Redis Database   │   │
│  │  (FastAPI)    │     │  (Persistent)     │   │
│  │               │     │                   │   │
│  │  - OAuth      │     │  - User tokens    │   │
│  │  - Chat tools │     │  - Settings       │   │
│  │  - GraphQL    │     │  - Default teams  │   │
│  └───────────────┘     └───────────────────┘   │
│         │                                       │
│         ▼                                       │
│  https://YOUR-APP.up.railway.app               │
└─────────────────────────────────────────────────┘
```

---

## 📡 API Endpoints

| Endpoint                     | Method | Description                    |
| ---------------------------- | ------ | ------------------------------ |
| `/`                          | GET    | Home page / App settings       |
| `/health`                    | GET    | Health check                   |
| `/auth/linear`               | GET    | Start OAuth flow               |
| `/auth/linear/callback`      | GET    | OAuth callback                 |
| `/setup/linear`              | GET    | Check setup status             |
| `/disconnect`                | GET    | Disconnect account             |
| `/tools/create_issue`        | POST   | Chat tool: Create issue        |
| `/tools/list_my_issues`      | POST   | Chat tool: List my issues      |
| `/tools/update_issue_status` | POST   | Chat tool: Update status       |
| `/tools/search_issues`       | POST   | Chat tool: Search issues       |
| `/tools/get_issue`           | POST   | Chat tool: Get issue details   |
| `/tools/add_comment`         | POST   | Chat tool: Add comment         |

---

## 🎨 Priority Levels

When creating issues, you can specify priority:

| Priority | Color  | Description                        |
| -------- | ------ | ---------------------------------- |
| 🔴 Urgent | Red    | Critical issues needing immediate attention |
| 🟠 High   | Orange | Important issues to address soon   |
| 🟡 Medium | Yellow | Standard priority issues           |
| 🔵 Low    | Blue   | Nice-to-have or backlog items      |
| ⚪ None   | Gray   | No priority set                    |

---

## 🐛 Troubleshooting

### "User not authenticated"

- Complete the Linear OAuth flow by clicking "Connect Linear" in app settings

### "No teams found"

- Ensure you have access to at least one team in your Linear workspace
- Try reconnecting your Linear account

### "Could not find issue"

- Verify the issue identifier is correct (e.g., "ENG-123")
- Ensure the issue exists in a team you have access to

### "Failed to update status"

- Check that the status name is valid for your team's workflow
- Try using standard names: "Backlog", "Todo", "In Progress", "Done"

---

## 📄 License

MIT License - feel free to modify and distribute.

---

## 🤝 Support

For issues or feature requests, please open an issue on GitHub or contact the Omi community.

---

Made with ❤️ for Omi

