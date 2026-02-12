# Twitter/X Omi Integration

Post tweets and manage your Twitter/X account through Omi chat.

## Features

- **Post Tweets** - Share updates with your followers
- **View Timeline** - See your home feed
- **Get Your Tweets** - View your recent posts
- **Get Mentions** - See who mentioned you
- **Search Tweets** - Find tweets about any topic
- **Like/Unlike Tweets** - Engage with content
- **Retweet** - Share tweets with your followers
- **Delete Tweets** - Remove your tweets
- **View Profiles** - Look up Twitter users

## Setup

### 1. Create Twitter Developer App

1. Go to [Twitter Developer Portal](https://developer.twitter.com/en/portal/projects-and-apps)
2. Create a new Project and App (or use existing)
3. Set up **User authentication settings**:
   - App permissions: **Read and write**
   - Type of App: **Web App**
   - Callback URI: Add your callback URL (see below)
   - Website URL: Your app website
4. Copy the **Client ID** and **Client Secret**

### 2. Deploy to Railway

1. Create a new project on [Railway](https://railway.app/)
2. Connect your GitHub repo or deploy from this folder
3. Add a **Redis** service to your project
4. Set environment variables:

```
TWITTER_CLIENT_ID=your_client_id
TWITTER_CLIENT_SECRET=your_client_secret
TWITTER_REDIRECT_URI=https://your-app.up.railway.app/auth/twitter/callback
```

5. Deploy! Railway will automatically:
   - Install dependencies from `requirements.txt`
   - Start the server using `railway.toml` config
   - Provide `PORT` and `REDIS_URL` environment variables

### 3. Update Twitter OAuth Redirect URI

After deployment, update your Twitter app's callback URL:

```
https://your-app.up.railway.app/auth/twitter/callback
```

## Omi App Configuration

When creating/updating the Omi app, use these URLs:

| Field | Value |
|-------|-------|
| **Setup URL** | `https://your-app.up.railway.app/?uid={{uid}}` |
| **Setup Completed URL** | `https://your-app.up.railway.app/setup/twitter?uid={{uid}}` |
| **Chat Tools Manifest URL** | `https://your-app.up.railway.app/.well-known/omi-tools.json` |

## API Endpoints

### Chat Tools (POST)

| Endpoint | Description |
|----------|-------------|
| `/tools/post_tweet` | Post a new tweet |
| `/tools/get_timeline` | Get home timeline |
| `/tools/get_my_tweets` | Get your own tweets |
| `/tools/get_mentions` | Get mentions |
| `/tools/search_tweets` | Search tweets |
| `/tools/like_tweet` | Like a tweet |
| `/tools/unlike_tweet` | Unlike a tweet |
| `/tools/retweet` | Retweet |
| `/tools/delete_tweet` | Delete a tweet |
| `/tools/get_user_profile` | Get user profile |

### OAuth & Setup (GET)

| Endpoint | Description |
|----------|-------------|
| `/` | Home page / setup UI |
| `/auth/twitter?uid=<uid>` | Start OAuth flow |
| `/auth/twitter/callback` | OAuth callback |
| `/setup/twitter?uid=<uid>` | Check setup status |
| `/disconnect?uid=<uid>` | Disconnect account |
| `/health` | Health check |
| `/.well-known/omi-tools.json` | Chat tools manifest |

## Local Development

1. Copy `.env.example` to `.env` and fill in your credentials
2. Set `TWITTER_REDIRECT_URI=http://localhost:8080/auth/twitter/callback`
3. Add this to your Twitter app's callback URIs
4. Install dependencies: `pip install -r requirements.txt`
5. Run: `python main.py`

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TWITTER_CLIENT_ID` | Twitter OAuth2 Client ID | Yes |
| `TWITTER_CLIENT_SECRET` | Twitter OAuth2 Client Secret | Yes |
| `TWITTER_REDIRECT_URI` | OAuth callback URL | Yes |
| `PORT` | Server port (default: 8080) | No |
| `REDIS_URL` | Redis connection URL | No (uses file storage if not set) |

## Example Chat Commands

- "Tweet: Just discovered this amazing AI assistant!"
- "Show my Twitter timeline"
- "Search Twitter for AI news"
- "Like the last tweet"
- "Who mentioned me on Twitter?"
- "Show @elonmusk's profile"
- "Delete my last tweet"

## Twitter API Rate Limits

Be aware of Twitter API rate limits:
- Tweets per 24 hours: Varies by account type
- Read operations: 300-900 requests per 15 minutes
- Search: 180 requests per 15 minutes

The integration handles rate limits gracefully and will return appropriate error messages.

## Note on Twitter API Access

This integration requires Twitter API v2 access. Depending on your Twitter Developer account tier:
- **Free tier**: Limited to 1,500 tweets per month, basic read access
- **Basic tier**: 3,000 tweets per month, more read access
- **Pro tier**: Higher limits, more features

Some features (like viewing timeline) may require elevated access.
