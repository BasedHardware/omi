# Microsoft 365 Omi Integration

Full-featured Microsoft 365 integration for Omi — bringing Outlook Mail, Outlook
Calendar, Microsoft Teams chats and meetings, SharePoint and OneDrive into
Omi's chat and conversation capabilities.

## Features

- **Outlook Mail** — list, search, read, send
- **Outlook Calendar** — list upcoming events, create events (optionally as Teams meetings), find free slots
- **Microsoft Teams** — list chats, send chat messages, list teams, create standalone online meetings
- **OneDrive / SharePoint** — list recent files, search, upload text files, read file content
- **Profile** — `Who am I?` / `/me`
- **OAuth 2.0** with Microsoft Entra ID (MSAL), token caching in Redis (fallback: in-memory)
- **Multi-tenant by default** (configurable)
- **Throttling-aware Graph client** with exponential backoff
- **Automatic manifest** — served at `/.well-known/omi-tools.json`

## Setup

### 1. Microsoft Azure App Registration

1. Go to [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **+ New registration**
2. Configure:
   - **Name**: `Omi Microsoft 365`
   - **Account types**: *Accounts in any organizational directory and personal Microsoft accounts* (multi-tenant)
   - **Redirect URI**: Web → `http://localhost:8080/auth/microsoft/callback` (adjust after deploy)
3. After creation, note the **Application (client) ID** and **Directory (tenant) ID** (`common` for multi-tenant).
4. Under **Certificates & secrets** → **+ New client secret** → save the **value** (not the id).
5. Under **API permissions** → **+ Add a permission** → **Microsoft Graph** → **Delegated** → add:

```
offline_access
User.Read
MailboxSettings.Read
Mail.Read
Mail.Send
Mail.ReadWrite
Calendars.ReadWrite
Chat.ReadWrite
ChannelMessage.Send
OnlineMeetings.ReadWrite
Team.ReadBasic.All
Files.ReadWrite.All
Sites.Read.All
People.Read
Contacts.Read
```

Click **Grant admin consent** if you are a tenant admin; otherwise users consent on first sign-in.

### 2. Deploy

This app is a vanilla FastAPI service. Any PaaS that supports Python + Redis works (Railway, Render, Fly, Heroku-style).

**Railway** (matches sibling apps in this repo):

1. Create a new project on [Railway](https://railway.app/)
2. Deploy from this folder (`plugins/omi-ms365-app`)
3. Add a **Redis** service
4. Set environment variables (see `.env.example`):

   ```
   MICROSOFT_CLIENT_ID=...
   MICROSOFT_CLIENT_SECRET=...
   MICROSOFT_TENANT_ID=common
   MICROSOFT_REDIRECT_URI=https://your-app.up.railway.app/auth/microsoft/callback
   APP_BASE_URL=https://your-app.up.railway.app
   SESSION_SECRET=<random 32+ char string>
   ```

5. Railway auto-installs `requirements.txt` and starts via `railway.toml`.
6. After deploy, update Azure → **Authentication** with the final redirect URI.

### 3. Register with Omi

Create or update your Omi app and set:

| Field | Value |
|---|---|
| **Setup URL** | `https://your-app.up.railway.app/setup/ms365?uid={{uid}}` |
| **Setup Completed URL** | `https://your-app.up.railway.app/setup_check?uid={{uid}}` |
| **Chat Tools Manifest URL** | `https://your-app.up.railway.app/.well-known/omi-tools.json` |

The manifest auto-populates absolute endpoint URLs based on `APP_BASE_URL`.

## Local development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, SESSION_SECRET

uvicorn main:app --reload --port 8080
```

Open `http://localhost:8080/setup/ms365?uid=test-user` to walk the OAuth flow.

Verify a tool:

```bash
curl -X POST http://localhost:8080/tools/get_me \
  -H "Content-Type: application/json" \
  -d '{"uid":"test-user","args":{}}'
```

## API endpoints

### Chat tools (POST `/tools/{tool_name}`)

| Tool | Description |
|---|---|
| `get_me` | Current user profile |
| `list_mail` | List recent mail |
| `search_mail` | Full-text search mail |
| `read_mail` | Read a single message |
| `send_mail` | Send a message |
| `list_calendar_events` | List upcoming events |
| `create_calendar_event` | Create event (optionally a Teams meeting) |
| `find_free_slots` | Find free slots across attendees |
| `list_chats` | List Teams chats |
| `send_chat_message` | Send a Teams chat message |
| `list_teams` | List Teams the user is a member of |
| `create_online_meeting` | Create a standalone Teams meeting |
| `list_recent_files` | Recent OneDrive / SharePoint files |
| `search_files` | Search files across OneDrive / SharePoint |
| `upload_text_file` | Upload a text file |
| `read_file_content` | Read a file's content |

### OAuth & setup (GET)

| Endpoint | Purpose |
|---|---|
| `/setup/ms365?uid=...` | Start OAuth flow |
| `/auth/microsoft/callback` | OAuth redirect target |
| `/setup_check?uid=...` | Return `{is_setup_completed: bool}` for Omi |
| `/.well-known/omi-tools.json` | Tool manifest Omi consumes |
| `/webhook/memory` | Memory webhook (no-op placeholder) |

## Required environment variables

| Variable | Purpose |
|---|---|
| `MICROSOFT_CLIENT_ID` | Azure App Registration client id |
| `MICROSOFT_CLIENT_SECRET` | Azure App Registration client secret |
| `MICROSOFT_TENANT_ID` | `common` for multi-tenant, or a specific tenant id |
| `MICROSOFT_REDIRECT_URI` | Must match Azure redirect URI exactly |
| `APP_BASE_URL` | Public base URL of this service |
| `SESSION_SECRET` | Random string used to sign OAuth state |
| `REDIS_URL` | Optional — Redis connection URL for token persistence |
| `LOG_LEVEL` | `INFO`, `DEBUG`, etc. |

## Project layout

```
omi-ms365-app/
├── main.py              # FastAPI app + tool dispatch
├── config.py            # Settings + Graph scope list
├── omi-tools.json       # Tool manifest Omi reads
├── services/
│   ├── auth.py          # Microsoft OAuth + MSAL
│   ├── storage.py       # Redis / in-memory token store
│   ├── graph_client.py  # Throttling-aware Graph HTTP client
│   ├── profile.py
│   ├── mail.py
│   ├── calendar.py
│   ├── teams.py
│   └── sharepoint.py
├── requirements.txt
├── Procfile
├── railway.toml
└── .env.example
```

## Extending

1. Add a function in `services/<area>.py` with signature `async def foo(user_id: str, ...)`.
2. Register it in `_TOOLS` in `main.py`.
3. Add its declaration to `omi-tools.json`.

## License

MIT.
