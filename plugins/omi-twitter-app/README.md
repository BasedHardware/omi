# 🐦 Twitter Voice Poster for OMI

Voice-activated Twitter posting through your OMI device. Simply say "Tweet Now" followed by your message, and it will be automatically posted to Twitter!

**Live Demo:** [omi-twitter.up.railway.app](https://omi-twitter.up.railway.app)

## ✨ Features

- **🎤 Voice-Activated** - Say "Tweet Now" and speak your message
- **🧠 AI-Powered** - Collects 3 segments, intelligently extracts and cleans your tweet
- **🔐 One-Time Auth** - Connect Twitter once, works forever (auto token refresh)
- **🤖 Smart Extraction** - AI knows what's the tweet vs side comments
- **🔕 Silent Collection** - Only notifies when tweet is posted
- **📱 Works 24/7** - Deployed on Railway with persistent storage

## 🚀 Quick Start

### For OMI Users

1. **Install the app** in your OMI mobile app
2. **Authenticate** your Twitter account (one-time)
3. **Start tweeting!**
   - Say: "Tweet Now, I love using OMI to tweet with my voice!"
   - The app collects your speech (up to 3 segments)
   - AI extracts and posts the tweet
   - You get a notification when it's posted! ✅

### Trigger Phrases

- "Tweet Now"
- "Post Tweet"
- "Send Tweet"
- "Tweet This"

### How It Works

**The app is smart about collecting your speech:**
1. Detects "Tweet Now" → Starts collecting
2. Automatically collects the next 2 segments (or waits for them)
3. Sends all 3 segments to AI
4. AI extracts the actual tweet, removes filler words
5. Posts to Twitter!
6. Notifies you once ✅

**Example:**
```
You: "Tweet Now, I just had"
     [collecting silently...]
You: "an incredible idea about"
     [collecting silently...]
You: "voice AI and social media!"
     → AI processes all 3 segments
     → Posts: "I just had an incredible idea about voice AI and social media!"
     → Notification sent! 🔔
```

## 🎯 OMI App Configuration

| Field | Value |
|-------|-------|
| **Webhook URL** | `https://omi-twitter.up.railway.app/webhook` |
| **App Home URL** | `https://omi-twitter.up.railway.app/` |
| **Auth URL** | `https://omi-twitter.up.railway.app/auth` |
| **Setup Completed URL** | `https://omi-twitter.up.railway.app/setup-completed` |

## 🛠️ Development Setup

### Prerequisites

- Python 3.10+
- Twitter Developer Account with API v2 access
- OpenAI API key
- OMI device and app

### Installation

```bash
# Clone the repository
git clone https://github.com/aaravgarg/omi-twitter-app.git
cd omi-twitter-app

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
# Twitter API Credentials (from developer.twitter.com)
TWITTER_API_KEY=your_api_key
TWITTER_API_SECRET=your_api_secret
TWITTER_CLIENT_ID=your_client_id
TWITTER_CLIENT_SECRET=your_client_secret

# OAuth Redirect URL
OAUTH_REDIRECT_URL=http://localhost:8000/auth/callback

# OpenAI API Key (for AI tweet extraction)
OPENAI_API_KEY=your_openai_key

# App Settings
APP_HOST=0.0.0.0
APP_PORT=8000
```

### Twitter Developer Setup

1. Go to [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Create a new app or use existing
3. Enable **OAuth 2.0**
4. Set permissions to **Read and Write**
5. Add callback URL: `http://localhost:8000/auth/callback` (for local dev)
6. Note your API credentials

### Run Locally

```bash
source venv/bin/activate
python main_simple.py
```

Visit `http://localhost:8000/test` to test!

## ☁️ Railway Deployment

### Quick Deploy

1. **Push to GitHub**
   ```bash
   git push origin main
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
   - Twitter Portal: Add same callback URL

5. **Configure OMI**
   - Use your Railway URLs in OMI app settings

### Railway Environment Variables

Add these in Railway dashboard:

```
TWITTER_API_KEY
TWITTER_API_SECRET
TWITTER_CLIENT_ID
TWITTER_CLIENT_SECRET
OPENAI_API_KEY
OAUTH_REDIRECT_URL=https://your-app.up.railway.app/auth/callback
APP_HOST=0.0.0.0
APP_PORT=8000
```

## 🧪 Testing

### Web Interface

Visit `https://omi-twitter.up.railway.app/test` to:
- Authenticate your Twitter account
- Test voice commands by typing
- See real-time logs
- Verify tweets are posting

### With OMI Device

1. Configure webhook URLs in OMI Developer Settings
2. Enable the integration
3. Authenticate Twitter
4. Say: "Tweet Now, This is a test!"
5. Wait for collection (silent)
6. Get notification when posted! 🎉

## 🧠 AI Processing

The app uses OpenAI for two things:

1. **Tweet Extraction** - Analyzes all 3 segments to extract what's actually the tweet
2. **Cleanup** - Removes filler words, fixes grammar, capitalizes properly

**Example:**
```
Input (3 segments):
"that this is amazing and um I think"
"it's really cool and oh wait"
"I need to remember to buy milk later"

AI Output:
"That this is amazing and I think it's really cool"
(Milk reminder correctly excluded!)
```

## 📊 How Segments Work

**OMI sends transcripts in segments** as you speak. The app:
- ✅ Detects "Tweet Now" trigger
- ✅ Collects exactly 3 segments
- ✅ Silent during collection (no spam)
- ✅ AI processes all 3 together
- ✅ One notification on completion

**Why 3 segments?**
- Gives you time to complete your thought
- Captures ~10-20 seconds of speech
- AI has full context for extraction
- Balances speed vs completeness

## 🔐 Security & Privacy

- ✅ Tokens stored securely with file persistence
- ✅ Auto token refresh (never expires)
- ✅ OAuth 2.0 authentication
- ✅ Environment variables for secrets
- ✅ Per-user token isolation
- ✅ HTTPS enforced in production

## 🐛 Troubleshooting

### "User not authenticated"
- Complete Twitter OAuth flow
- Check Railway logs for auth errors
- Re-authenticate if needed

### "Tweet not posting"
- Check Railway logs for errors
- Verify Twitter app has "Read and Write" permissions
- Ensure you said "Tweet Now" trigger phrase
- Wait for all 3 segments to be collected

### "Session resets between segments"
- This should be fixed! Session uses consistent ID per user
- Check Railway logs - should see same session_id
- Contact support if issue persists

### "Railway deployment fails"
- Verify all environment variables are set
- Check build logs for specific errors
- Ensure `OAUTH_REDIRECT_URL` is set correctly

## 📁 Project Structure

```
omi-twitter-app/
├── main_simple.py           # FastAPI application
├── twitter_client.py        # Twitter API integration
├── tweet_detector.py        # AI-powered tweet detection & extraction
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
| `/` | GET | Setup instructions & info |
| `/auth` | GET | Start Twitter OAuth flow |
| `/auth/callback` | GET | OAuth callback handler |
| `/setup-completed` | GET | Check if user authenticated |
| `/webhook` | POST | Real-time transcript processor |
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

- **Issues**: [GitHub Issues](https://github.com/aaravgarg/omi-twitter-app/issues)
- **OMI Docs**: [docs.omi.me](https://docs.omi.me)
- **Twitter API**: [developer.twitter.com/en/docs](https://developer.twitter.com/en/docs)

## 🎉 Credits

Built for the [OMI](https://omi.me) ecosystem.

- **OMI Team** - Amazing wearable AI platform
- **Twitter API** - Social media integration
- **OpenAI** - Intelligent text processing

---

**Made with ❤️ for voice-first social media**

**Deployed at:** [omi-twitter.up.railway.app](https://omi-twitter.up.railway.app)

