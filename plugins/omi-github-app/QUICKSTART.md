# 🚀 Quick Start Guide

## 5-Minute Setup

### 1. Install Dependencies (1 min)

```bash
cd /Users/aaravgarg/omi-ai/Code/apps/github
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create GitHub OAuth App (2 min)

1. Go to https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in:
   - Name: `OMI GitHub Issues`
   - Homepage: `http://localhost:8000`
   - Callback: `http://localhost:8000/auth/callback`
4. Click "Register application"
5. Copy Client ID and Client Secret

### 3. Get OpenAI API Key (1 min)

1. Go to https://platform.openai.com/api-keys
2. Create new secret key
3. Copy the key

### 4. Configure Environment (1 min)

```bash
cp .env.example .env
nano .env  # or use any editor
```

Add your keys:
```env
GITHUB_CLIENT_ID=your_github_client_id_here
GITHUB_CLIENT_SECRET=your_github_client_secret_here
OPENAI_API_KEY=sk-...your_openai_key_here
OAUTH_REDIRECT_URL=http://localhost:8000/auth/callback
APP_HOST=0.0.0.0
APP_PORT=8000
```

### 5. Run the App (30 sec)

```bash
python main.py
```

You should see:
```
🐙 OMI GitHub Issues Integration
==================================================
✅ Using file-based storage
🚀 Starting on 0.0.0.0:8000
==================================================
```

## Test It Out

### Option 1: Web Interface

1. Open http://localhost:8000/test
2. Click "Authenticate GitHub"
3. Select a repository
4. Type a test command:
   ```
   Feedback Post, testing the app to make sure it works correctly with all the features and settings
   ```
5. Click "Send Command"
6. Check your GitHub repo for the new issue!

### Option 2: With OMI Device

1. Open http://localhost:8000/?uid=YOUR_OMI_UID
2. Click "Connect GitHub Account"
3. Select target repository
4. In OMI app, configure:
   - Webhook: `http://localhost:8000/webhook`
   - Auth: `http://localhost:8000/auth`
   - Setup Check: `http://localhost:8000/setup-completed`
5. Say to your OMI: "Feedback Post, the app is working great..."
6. Wait for notification with issue link!

## Common Issues

### Port 8000 already in use
```bash
# Change port in .env
APP_PORT=8001

# Or kill existing process
lsof -ti:8000 | xargs kill -9
```

### GitHub OAuth redirect mismatch
Make sure `.env` has:
```
OAUTH_REDIRECT_URL=http://localhost:8000/auth/callback
```
And GitHub OAuth app has the same callback URL.

### No repositories showing up
- Make sure you have at least one GitHub repo
- Click "Refresh Repos" on the homepage
- Check that OAuth app has `repo` scope

## Next Steps

### Deploy to Production

1. **Railway** (recommended):
   ```bash
   # Push to GitHub
   git init
   git add .
   git commit -m "Initial commit"
   git push
   
   # Deploy on railway.app
   # Add environment variables
   # Update OAUTH_REDIRECT_URL to Railway URL
   ```

2. **Update GitHub OAuth app**:
   - Change callback to: `https://your-app.up.railway.app/auth/callback`

3. **Configure OMI**:
   - Update webhook URLs to Railway domain

### Customize

- **Change trigger phrase**: Edit `TRIGGER_PHRASES` in `issue_detector.py`
- **Adjust segments**: Change `>= 5` in `main.py` to collect more/less
- **Custom labels**: Modify `labels=["voice-feedback"]` in webhook handler
- **UI colors**: Edit `get_mobile_css()` in `main.py`

## Architecture Overview

```
OMI Device
    ↓ (voice) "Feedback Post, ..."
Webhook Endpoint (/webhook)
    ↓ (collect 5 segments)
Issue Detector (AI)
    ↓ (generate title + description)
GitHub API
    ↓ (create issue)
User Notification ✅
```

## File Overview

- `main.py` - FastAPI app, endpoints, UI
- `github_client.py` - GitHub API calls
- `issue_detector.py` - AI processing
- `simple_storage.py` - User data persistence

## Support

- Check logs: Look at terminal output
- Enable debug: Add `print()` statements
- Test endpoint: `http://localhost:8000/health`
- Check storage: `cat users_data.json`

---

**Ready to go!** 🎉

Say "Feedback Post" to your OMI and watch the magic happen.

