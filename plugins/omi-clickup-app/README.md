# ClickUp Voice Task Creator for OMI

Voice-activated ClickUp task creation through OMI. Say trigger phrase + task details → AI creates task automatically.

## Capabilities

- **Voice-activated task creation** with 4 trigger phrases
- **AI extraction**: task name, description, list (fuzzy match), priority, due date/time
- **Timezone-aware** date parsing (13+ timezones)
- **Smart collection**: collects 2-5 segments OR times out after 5s silence
- **OAuth 2.0** authentication with persistent storage
- **Mobile-first UI** for settings management
- **OMI notifications**: instant confirmation when tasks are created

## Trigger & Timeout Mechanism

**Trigger phrases**: `create clickup task`, `create click up task`, `add clickup task`, `add click up task`

**Collection flow**:
1. Detects trigger phrase → starts collecting transcripts
2. Collects **2-5 segments max** OR **stops after 5+ second silence**
3. Minimum 2 segments required (trigger + content)
4. AI processes all segments together
5. Single notification on completion

**Example**:
```
You: "Create ClickUp task fix login bug by tomorrow 5pm"
     [segment 1/5...]
You: "users can't sign in high priority"
     [segment 2/5...]
     [5 second pause → processes 2 segments]
     
✅ Task created: "Fix login bug" (Priority: High, Due: Oct 31 5pm)
```

## Replication Guide

### Prerequisites
- Python 3.10+
- ClickUp workspace (admin access)
- OpenAI API key
- Deployment platform (Railway/Heroku/etc)

### 1. Environment Setup

Create `.env` file:
```env
# ClickUp OAuth (from app.clickup.com/settings/apps)
CLICKUP_CLIENT_ID=your_client_id
CLICKUP_CLIENT_SECRET=your_client_secret
OAUTH_REDIRECT_URL=https://your-app-url.com/auth/callback

# OpenAI for AI extraction
OPENAI_API_KEY=your_openai_key

# OMI API for notifications
OMI_APP_ID=your_omi_app_id
OMI_APP_SECRET=your_omi_app_secret

# Server config
APP_HOST=0.0.0.0
APP_PORT=8000
```

### 2. ClickUp OAuth App

1. Go to [ClickUp Apps](https://app.clickup.com/settings/apps)
2. Create new app
3. Set redirect URL: `https://your-app-url.com/auth/callback`
4. Copy Client ID + Secret to `.env`

### 3. Local Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Test at: `http://localhost:8000/test?dev=true`

### 4. Deploy to Railway

```bash
# Push to GitHub
git init && git add . && git commit -m "Initial"
git remote add origin <your-repo-url>
git push -u origin main

# On Railway:
# 1. New Project → Deploy from GitHub
# 2. Add environment variables from .env
# 3. Generate domain (Settings → Networking)
# 4. Update OAUTH_REDIRECT_URL to Railway domain
```

### 5. Configure OMI App

In OMI Developer Settings:

| Field | Value |
|-------|-------|
| Webhook URL | `https://your-app-url.com/webhook` |
| App Home URL | `https://your-app-url.com/` |
| Auth URL | `https://your-app-url.com/auth` |
| Setup Completed URL | `https://your-app-url.com/setup-completed` |

### 6. Usage

1. Install app in OMI mobile app
2. Authenticate ClickUp workspace
3. Set timezone in settings (optional: default list)
4. Say: "Create ClickUp task fix bug by tomorrow high priority"

## Project Structure

```
clickup/
├── main.py              # FastAPI app + UI + endpoints
├── clickup_client.py    # ClickUp API wrapper
├── task_detector.py     # AI task extraction (OpenAI)
├── simple_storage.py    # File-based user storage
├── requirements.txt     # Dependencies
├── railway.toml         # Railway deployment config
├── runtime.txt          # Python version
└── Procfile            # Process config
```

## Adapting for Other Integrations

**Core pattern** (reusable):
1. **Trigger detection** in webhook handler (`/webhook`)
2. **Segment collection** with timeout tracking (`asyncio` background task)
3. **AI extraction** using OpenAI with structured prompts
4. **OAuth flow** (`/auth`, `/auth/callback`)
5. **Settings UI** with storage persistence

**To adapt**:
- Replace `clickup_client.py` with target service API
- Update AI prompt in `task_detector.py` for different data structure
- Modify OAuth endpoints for service's auth flow
- Adjust trigger phrases and collection logic as needed

## Key Dependencies

```txt
fastapi==0.104.1
uvicorn==0.24.0
openai==1.3.7
httpx==0.25.2
pytz==2023.3
python-dotenv==1.0.0
requests==2.31.0
```

## License

MIT License

## Offline list-discovery regression

From the repository root, run `python3 plugins/omi-clickup-app/test_clickup_client.py`.
The stdlib suite imports the production client with fixture-only HTTP and dotenv
doubles. It covers folder-only and mixed workspaces, multiple spaces, empty folders,
and failed folder requests while preserving successfully discovered lists.
The same command runs through the local/CI checks manifest. No credentials or
provider access are needed. OAuth setup and manual **Refresh Lists** both consume `get_all_lists`,
which now includes folder-contained lists with their folder and space IDs.

### List-discovery request budget

For one workspace with `S` returned spaces and `F` returned folders across those
spaces, a successful `get_all_lists` enumeration makes `1 + 2S + F` sequential
HTTP requests: one to enumerate spaces, two per space (folderless lists and
folders), and one per folder to fetch its lists, including empty folders.
For example, 10 spaces containing 100 folders require 121 discovery requests.
This excludes the callers' workspace/member requests and OAuth token/user requests.

Discovery runs during OAuth setup (`/auth/callback`) and when the user presses
**Refresh Lists** (`POST /refresh-lists`), not in a background token-refresh job.
The resulting list selection data is stored for subsequent use; manual refresh
performs discovery again. Large workspaces can therefore have slow setup/refresh
and encounter provider rate limits. Discovery currently has no parallel fetching,
retry/backoff, or explicit HTTP timeout, so its duration is not bounded by the
client. This change does not improve that performance behavior.

The budget assumes successful space/folder enumeration. Failed enumeration skips
its descendants, reducing the attempted requests and potentially returning only
partial results. Failed individual list requests also leave those lists out while
preserving lists discovered elsewhere; a shorter response is not proof that all
workspace lists were discovered.
