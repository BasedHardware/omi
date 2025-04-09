# OMI-Composio Integration

This plugin allows users to connect various services through Composio to extract memories and import them into their OMI account.

## Features

- Connect Notion accounts via OAuth
- Extract memories and facts from Notion pages and databases
- Import extracted memories into OMI
- Mobile-optimized UI for easy use on mobile devices

## Requirements

- Python 3.8+
- OMI App with API credentials
- Notion OAuth credentials

## Setup Instructions

### 1. Set up OMI App

1. Create a new OMI app in the OMI mobile app
2. Enable the "External Integration" capability
3. Under "Integration Actions," enable "Create Memories"
4. Generate an API key
5. Note down your APP_ID and API_KEY

### 2. Set up Notion Integration

1. Go to [Notion Developers](https://www.notion.so/my-integrations) and create a new integration
2. Set the "Redirect URI" to your callback URL (e.g., `https://your-domain.com/api/notion/callback`)
3. Note down your Client ID and Client Secret

### 3. Configuration

1. Copy `.env.template` to `.env`
2. Fill in your OMI and Notion credentials:
   ```
   OMI_APP_ID=your_app_id_here
   OMI_API_KEY=your_api_key_here
   NOTION_CLIENT_ID=your_notion_client_id_here
   NOTION_CLIENT_SECRET=your_notion_client_secret_here
   NOTION_REDIRECT_URI=https://your-domain.com/api/notion/callback
   ```

### 4. Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --reload
```

### 5. Docker Deployment

```bash
# Build the Docker image
docker build -t omi-composio .

# Run the container
docker run -p 8000:8000 --env-file .env omi-composio
```

## Usage

1. Navigate to the homepage
2. Connect your Notion account
3. Search for pages in your Notion workspace
4. Select a page to extract memories from
5. Review and import memories into OMI

## How It Works

1. The plugin authenticates users with Notion via OAuth
2. Upon selection of a Notion page, the plugin extracts the text content
3. The text is analyzed to identify potential memories/facts about the user
4. Memories are formatted as "User likes...", "User enjoys...", etc.
5. These memories are then imported into OMI using the Integration API

## Composio Integration

This plugin is designed to work with Composio, a platform for connecting various tools and services. Composio provides a unified interface for users to connect their accounts and manage data flows between different platforms.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 