# 💬 Slack Voice Messenger for OMI

Voice-activated Slack messaging through your OMI device. Simply say "Send message to [channel]" followed by your message, and AI will automatically post it to the right Slack channel!

## ✨ Features

- **🎤 Voice-Activated** - Say "Send message" and speak naturally
- **🧠 AI-Powered Channel Matching** - AI intelligently matches spoken channel names to your workspace
- **🔐 OAuth Authentication** - Secure Slack OAuth 2.0 integration
- **📦 Channel Selection** - Set a default channel or specify in voice command
- **⚙️ Flexible Settings** - Change channels anytime from mobile-first homepage
- **🤖 Smart Message Extraction** - AI cleans up filler words and formats professionally
- **🔕 Silent Collection** - Only notifies when message is sent
- **📱 Mobile-First UI** - Beautiful responsive Slack-themed design

## 🚀 Quick Start

### For OMI Users

1. **Install the app** in your OMI mobile app
2. **Authenticate** your Slack workspace (one-time)
3. **Select default channel** (optional - you can specify in voice)
4. **Start messaging!**
   - Say: "Send message to general saying hello team!"
   - Say: "Post in marketing that the campaign is live"
   - Say: "Slack message to random saying great idea!"

### Trigger Phrases (ONLY these 3)

- **"Send Slack message"** - "Send Slack message to general saying..."
- **"Post Slack message"** - "Post Slack message in marketing that..."
- **"Post in Slack"** - "Post in Slack to random saying..."

### How It Works

**The app intelligently processes your voice commands:**
1. Detects trigger phrase → Starts collecting
2. Collects up to 5 segments OR stops if 5+ second gap detected
3. AI extracts:
   - Channel name (fuzzy matches to your workspace channels)
   - Message content (cleaned and formatted)
4. Fetches fresh channel list automatically (new channels work immediately!)
5. Posts message to Slack
6. Notifies you with confirmation! 🎉

**Example:**
```
You: "Send Slack message to general saying hello team"
     [collecting segment 1/5...]
You: "hope everyone is having a great day"
     [collecting segment 2/5...]
     [5+ second pause - timeout!]
     → AI processes 2 segments
     
AI Extracted:
Channel: #general
Message: "Hello team, hope everyone is having a great day."

     → Message sent! 🔔
```

## 🎯 OMI App Configuration

| Field | Value |
|-------|-------|
| **Webhook URL** | `https://your-app.up.railway.app/webhook` |
| **App Home URL** | `https://your-app.up.railway.app/` |
| **Auth URL** | `https://your-app.up.railway.app/auth` |
| **Setup Completed URL** | `https://your-app.up.railway.app/setup-completed` |

## 🛠️ Development Setup

### Prerequisites

- Python 3.10+
- Slack workspace with admin access
- OpenAI API key
- OMI device and app

### Installation

```bash
# Clone the repository
cd slack

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
```

### Configuration

Create `.env` file with:

```env
# Slack OAuth Credentials (from api.slack.com/apps)
SLACK_CLIENT_ID=your_client_id
SLACK_CLIENT_SECRET=your_client_secret

# OAuth Redirect URL
OAUTH_REDIRECT_URL=http://localhost:8000/auth/callback

# OpenAI API Key (for AI channel matching & message extraction)
OPENAI_API_KEY=your_openai_key

# App Settings
APP_HOST=0.0.0.0
APP_PORT=8000
```

### Slack App Setup

1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Enter app name and select workspace
4. Navigate to "OAuth & Permissions"
5. Add scopes:
   - `channels:read` - View public channels
   - `chat:write` - Send messages
   - `groups:read` - View private channels
   - `users:read` - View user info
6. Set redirect URL: `http://localhost:8000/auth/callback`
7. Copy Client ID and Client Secret to `.env`

### Run Locally

```bash
source venv/bin/activate
python main.py
```

Visit `http://localhost:8000/test?dev=true` to test!

## ☁️ Railway Deployment

### Quick Deploy

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/BasedHardware/omi-slack-app.git
   git branch -M main
   git push -u origin main
   ```

2. **Deploy on Railway**
   - Go to [railway.app](https://railway.app)
   - New Project → Deploy from GitHub
   - Select your repo
   - Add environment variables (from your `.env`)

3. **Get your URL**
   - Settings → Networking → Generate Domain
   - You'll get: `your-app.up.railway.app`

4. **Update OAuth Redirect**
   - Railway Variables: `OAUTH_REDIRECT_URL=https://your-app.up.railway.app/auth/callback`
   - Slack App: Update redirect URL to same

5. **Configure OMI**
   - Use your Railway URLs in OMI app settings

### Railway Environment Variables

Add these in Railway dashboard:

```
SLACK_CLIENT_ID
SLACK_CLIENT_SECRET
OPENAI_API_KEY
OAUTH_REDIRECT_URL=https://your-app.up.railway.app/auth/callback
APP_HOST=0.0.0.0
APP_PORT=8000
PYTHONUNBUFFERED=1
```

**Note**: `PYTHONUNBUFFERED=1` ensures instant log output (no buffering delays)

## 🧪 Testing

### Web Interface

Visit `https://your-app.up.railway.app/test?dev=true` to:
- Authenticate your Slack workspace
- Test voice commands by typing
- See real-time logs
- Verify messages are posting

### With OMI Device

1. Configure webhook URLs in OMI Developer Settings
2. Enable the integration
3. Authenticate Slack and select default channel (optional)
4. Say: "Send message to general saying hello team!"
5. Wait for AI processing (silent)
6. Get notification with confirmation! 🎉

## 🧠 AI Processing

The app uses OpenAI for intelligent processing:

1. **Channel Matching** - Fuzzy matches spoken channel names to workspace channels
2. **Message Extraction** - Extracts clean message content from voice segments
3. **Cleanup** - Removes filler words, fixes grammar, proper formatting

**Example Transformation:**

```
Input (3 segments):
"to general saying um hello team hope you're all um doing great today"

AI Output:
Channel: #general (matched from "general")
Message: "Hello team, hope you're all doing great today"
```

## 📊 How Segments Work

**OMI sends transcripts in segments** as you speak. The app:
- ✅ Detects trigger phrase (Send Slack message / Post Slack message / Post in Slack)
- ✅ Collects up to 5 segments MAX
- ✅ Processes early if 5+ second gap detected (minimum 2 segments)
- ✅ Silent during collection (no spam)
- ✅ AI processes all collected segments together
- ✅ One notification on completion

**Smart Collection:**
- **Max segments:** 5 (including trigger)
- **Timeout:** 5 seconds of silence → processes immediately
- **Minimum:** 2 segments (trigger + content)
- **Duration:** ~5-20 seconds depending on speech
- **Auto-refresh:** Fetches latest channels every time (new channels work immediately!)

## 📱 Channel Management

### Specifying Channel in Voice

You can always specify the channel in your voice command:
- "Send message to **general** saying hello"
- "Post in **marketing** that campaign is live"
- "Message to **engineering** about the bug fix"

AI will fuzzy match to your workspace channels!

### Using Default Channel

Set a default channel in settings, then just say:
- "Send message saying quick update for everyone"
- Message goes to your default channel

### Refreshing Channel List

The app **automatically fetches fresh channels** every time you send a message, so new channels work immediately without manual refresh!

You can also manually refresh:
- Click "Refresh Channels" button on homepage
- Or re-authenticate to get latest channels

### Switching Workspaces

Click "Switch Workspace" to:
- Connect to a different Slack workspace
- Re-authenticate with new team
- Switch between multiple workspaces easily

## 🔐 Security & Privacy

- ✅ OAuth 2.0 authentication (no password storage)
- ✅ Tokens stored securely with file persistence
- ✅ Per-user token isolation
- ✅ HTTPS enforced in production
- ✅ State parameter for CSRF protection
- ✅ Secure scopes: minimal required permissions

## 🐛 Troubleshooting

### "User not authenticated"
- Complete Slack OAuth flow
- Check Railway logs for auth errors
- Re-authenticate if needed

### "No channel specified and no default channel set"
- Visit app homepage
- Select a default channel OR
- Specify channel in voice command

### "Message not sending"
- Check Railway logs for errors
- Verify channel exists and bot has access
- Ensure Slack app has correct scopes
- Check Slack API rate limits

### "Channel not found"
- Check channel name pronunciation
- AI does fuzzy matching but might need clearer speech
- Use "Refresh Channels" to update list
- Set as default channel in settings

### "Railway deployment fails"
- Verify all environment variables are set
- Check build logs for specific errors
- Ensure `OAUTH_REDIRECT_URL` matches Slack app

## 📁 Project Structure

```
slack/
├── main.py                  # FastAPI application with mobile-first UI
├── slack_client.py          # Slack API integration
├── message_detector.py      # AI-powered message & channel detection
├── simple_storage.py        # File-based storage (users & sessions)
├── requirements.txt         # Python dependencies
├── railway.toml            # Railway deployment config
├── runtime.txt             # Python version
├── Procfile                # Alternative deployment platforms
├── .env.example            # Environment template
├── .gitignore             # Git ignore rules
├── LICENSE                # MIT License
└── README.md              # This file
```

## 🔧 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Homepage with channel selection (mobile-first) |
| `/auth` | GET | Start Slack OAuth flow |
| `/auth/callback` | GET | OAuth callback handler |
| `/setup-completed` | GET | Check if user authenticated |
| `/webhook` | POST | Real-time transcript processor |
| `/update-channel` | POST | Update selected default channel |
| `/refresh-channels` | POST | Refresh channel list |
| `/test` | GET | Web testing interface |
| `/health` | GET | Health check |

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🆘 Support

- **OMI Docs**: [docs.omi.me](https://docs.omi.me)
- **Slack API**: [api.slack.com/docs](https://api.slack.com/docs)

## 🎉 Credits

Built for the [OMI](https://omi.me) ecosystem.

- **OMI Team** - Amazing wearable AI platform
- **Slack** - Team communication platform
- **OpenAI** - Intelligent text processing

---

**Made with ❤️ for voice-first team communication**

**Features:**
- 🎤 Voice-activated Slack messaging
- 🧠 AI-powered channel matching
- 📱 Mobile-first workspace management
- 🔐 Secure Slack OAuth integration
- ⚡ Real-time processing with Railway deployment

