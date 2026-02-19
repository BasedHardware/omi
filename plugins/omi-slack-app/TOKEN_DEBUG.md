# Debugging Bot vs User Token Issue

## Problem
Messages are posting as BOT instead of USER on Railway (but worked locally).

## Root Causes

### 1. **Incorrect `as_user` Parameter**
- The `as_user=True` parameter is **deprecated** and can cause issues
- With user tokens (xoxp-*), messages automatically post as the user
- This parameter was removed in the fix

### 2. **Bot Token vs User Token**
Slack has two types of tokens:
- **User Token** (xoxp-*): Posts messages as the authenticated user ✅
- **Bot Token** (xoxb-*): Posts messages as the bot app ❌

### 3. **Slack App Configuration Issue**
If the app has **Bot Token Scopes** configured in Slack, it may default to bot tokens even when user scopes are requested.

## How to Verify Token Type

After re-deploying, check the Railway logs when authenticating:

### ✅ Good (User Token):
```
✅ Using USER token (messages will appear as user)
✅ User token starts with: xoxp-...
🔑 Sending with USER token: xoxp-...
✅ Message posted as USER
```

### ❌ Bad (Bot Token):
```
⚠️ WARNING: Using BOT token (user token not available)
⚠️ This means messages will post as BOT, not as USER
🔑 Sending with BOT token: xoxb-...
⚠️ Message posted as BOT (bot_id: ...)
```

## Solutions

### Step 1: Re-authenticate on Railway
Users who authenticated before the fix need to **re-authenticate**:
1. Go to your Railway app URL
2. Click "Logout & Clear Data"
3. Authenticate again with "Connect Slack Workspace"

### Step 2: Check Slack App Settings
If still posting as bot, verify your Slack App configuration at https://api.slack.com/apps:

1. **OAuth & Permissions** page:
   - **User Token Scopes** should have:
     - `channels:read`
     - `chat:write`
     - `groups:read`
     - `users:read`
   
   - **Bot Token Scopes** should be **EMPTY** or minimal
     - If bot scopes include `chat:write`, Slack may prioritize bot token
     - Consider removing bot scopes entirely

2. **App Manifest** (Settings > App Manifest):
   ```yaml
   oauth_config:
     scopes:
       user:
         - channels:read
         - chat:write
         - groups:read
         - users:read
       # bot: []  # Leave empty or remove
   ```

### Step 3: Check Environment Variables
Ensure Railway has the same Slack app credentials as local:
- `SLACK_CLIENT_ID`
- `SLACK_CLIENT_SECRET`
- Both should match the app at api.slack.com/apps

## Token Prefixes
- `xoxp-*` = User token (posts as user) ✅
- `xoxb-*` = Bot token (posts as bot) ❌
- `xoxa-*` = App-level token
- `xoxr-*` = Refresh token

## Testing
Use the test interface with `?dev=true`:
```
https://your-railway-app.railway.app/test?dev=true
```

Check logs for token type when sending messages.

## More Info
- [Slack OAuth Docs](https://api.slack.com/authentication/oauth-v2)
- [User vs Bot Tokens](https://api.slack.com/authentication/token-types)

