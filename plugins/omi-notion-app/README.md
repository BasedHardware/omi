# Notion Omi Integration

Manage your Notion workspace through Omi chat - search pages, create content, query databases, and more.

## Features

- **Search** - Find pages and databases in your workspace
- **List Pages** - View recently edited pages
- **Create Pages** - Add new notes and content
- **Update Pages** - Modify titles and archive pages
- **Append Content** - Add text to existing pages
- **List Databases** - See all your databases
- **Query Databases** - View database entries

## Setup

### 1. Create Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click "New integration"
3. Fill in the basic information:
   - Name: "Omi Integration"
   - Associated workspace: Select your workspace
4. Under "Capabilities", ensure these are enabled:
   - Read content
   - Update content
   - Insert content
5. Under "OAuth Domain & URIs":
   - Redirect URIs: Add your callback URL (see below)
6. Click "Submit"
7. Copy the **OAuth client ID** and **OAuth client secret**

### 2. Deploy to Railway

1. Create a new project on [Railway](https://railway.app/)
2. Connect your GitHub repo or deploy from this folder
3. Add a **Redis** service to your project
4. Set environment variables:

```
NOTION_CLIENT_ID=your_client_id
NOTION_CLIENT_SECRET=your_client_secret
NOTION_REDIRECT_URI=https://your-app.up.railway.app/auth/notion/callback
```

5. Deploy! Railway will automatically:
   - Install dependencies from `requirements.txt`
   - Start the server using `railway.toml` config
   - Provide `PORT` and `REDIS_URL` environment variables

### 3. Update Notion OAuth Redirect URI

After deployment, update your Notion integration with the actual Railway URL:

```
https://your-app.up.railway.app/auth/notion/callback
```

## Omi App Configuration

When creating/updating the Omi app, use these URLs:

| Field | Value |
|-------|-------|
| **Setup URL** | `https://your-app.up.railway.app/?uid={{uid}}` |
| **Setup Completed URL** | `https://your-app.up.railway.app/setup/notion?uid={{uid}}` |
| **Chat Tools Manifest URL** | `https://your-app.up.railway.app/.well-known/omi-tools.json` |

## API Endpoints

### Chat Tools (POST)

| Endpoint | Description |
|----------|-------------|
| `/tools/search` | Search pages and databases |
| `/tools/list_pages` | List recent pages |
| `/tools/get_page` | Get page details and content |
| `/tools/create_page` | Create a new page |
| `/tools/update_page` | Update page properties |
| `/tools/append_content` | Add content to a page |
| `/tools/list_databases` | List all databases |
| `/tools/query_database` | Query database entries |

### OAuth & Setup (GET)

| Endpoint | Description |
|----------|-------------|
| `/` | Home page / setup UI |
| `/auth/notion?uid=<uid>` | Start OAuth flow |
| `/auth/notion/callback` | OAuth callback |
| `/setup/notion?uid=<uid>` | Check setup status |
| `/disconnect?uid=<uid>` | Disconnect account |
| `/health` | Health check |
| `/.well-known/omi-tools.json` | Chat tools manifest |

## Local Development

1. Copy `.env.example` to `.env` and fill in your credentials
2. Set `NOTION_REDIRECT_URI=http://localhost:8080/auth/notion/callback`
3. Add this to your Notion integration's redirect URIs
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python main.py`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `NOTION_CLIENT_ID` | Notion OAuth Client ID | Yes |
| `NOTION_CLIENT_SECRET` | Notion OAuth Client Secret | Yes |
| `NOTION_REDIRECT_URI` | OAuth callback URL | Yes |
| `PORT` | Server port (default: 8080) | No |
| `REDIS_URL` | Redis connection URL | No (uses file storage if not set) |

## Example Chat Commands

- "Search for meeting notes in Notion"
- "Show my recent Notion pages"
- "Create a new page called Project Ideas"
- "Add 'remember to call John' to my todo page"
- "Show my databases"
- "What's in my Tasks database?"

## Note on Page Permissions

When users connect their Notion workspace, they must grant access to specific pages. The integration can only access pages that users have explicitly shared with it during the OAuth flow.
