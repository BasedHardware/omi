# 🐙 GitHub Issues Voice Poster for OMI

Voice-activated GitHub issue creation through your OMI device. Simply say "Feedback Post" followed by your detailed problem description, and AI will automatically create a properly formatted GitHub issue!

> **Test Change**: This is a test modification for merge testing purposes.

## ✨ Features

- **🎤 Voice-Activated** - Say "Feedback Post" and describe your problem
- **🧠 AI-Powered** - Collects 5 segments for detailed feedback, generates title + description
- **🔐 OAuth Authentication** - Secure GitHub OAuth 2.0 integration
- **📦 Repository Selection** - Choose which repo receives issues during setup
- **⚙️ Flexible Settings** - Change target repository anytime from mobile-first homepage
- **🤖 Smart Formatting** - AI extracts key info and formats professional issues
- **🔕 Silent Collection** - Only notifies when issue is created
- **📱 Mobile-First UI** - Beautiful responsive design for all devices

## 🚀 Quick Start

### For OMI Users

1. **Install the app** in your OMI mobile app
2. **Authenticate** your GitHub account (one-time)
3. **Select repository** where issues should be created
4. **Start reporting issues!**
   - Say: "Feedback Post, the app keeps crashing when I upload photos..."
   - Keep describing the problem naturally for 15-20 seconds
   - AI processes your speech and creates a formatted issue
   - You get a notification with the issue link! ✅

### Trigger Phrases

- "Feedback Post"
- "Create Issue"
- "Report Issue"
- "File Issue"
- "New Issue"

### How It Works

**The app intelligently collects and processes your feedback:**
1. Detects "Feedback Post" → Starts collecting
2. Automatically collects 5 segments (15-20 seconds of detailed speech)
3. Sends all segments to AI
4. AI generates professional title and detailed description
5. Creates GitHub issue with "voice-feedback" label
6. Notifies you with issue link! 🎉

**Example:**
```
You: "Feedback Post, the search function isn't working"
     [collecting silently...]
You: "when I type in the search bar nothing happens"
     [collecting silently...]
You: "I've tried on both Chrome and Safari"
     [collecting silently...]
You: "and it worked fine last week but now"
     [collecting silently...]
You: "it's completely broken on all browsers"
     → AI processes all 5 segments
     
AI Generated Issue:
Title: "Search function not working across browsers"
Description: 
The search function is currently not working. When typing in the search bar, 
no results appear. This issue has been tested on both Chrome and Safari browsers. 
The search functionality was working correctly last week but is now completely 
non-functional across all browsers.

     → Issue created! 🔔
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
- GitHub account
- OpenAI API key
- OMI device and app

### Installation

```bash
# Clone the repository
cd github

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
# GitHub OAuth Credentials (from github.com/settings/developers)
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret

# OAuth Redirect URL
OAUTH_REDIRECT_URL=http://localhost:8000/auth/callback

# OpenAI API Key (for AI issue generation)
OPENAI_API_KEY=your_openai_key

# App Settings
APP_HOST=0.0.0.0
APP_PORT=8000
```

### GitHub OAuth App Setup

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Fill in:
   - **Application name:** "OMI GitHub Issues"
   - **Homepage URL:** `http://localhost:8000` (or your deployment URL)
   - **Authorization callback URL:** `http://localhost:8000/auth/callback`
4. Click "Register application"
5. Copy **Client ID** and **Client Secret** to your `.env`
6. For production: Update callback URL to your Railway/deployment URL

### Run Locally

```bash
source venv/bin/activate
python main.py
```

Visit `http://localhost:8000/test` to test!

## ☁️ Railway Deployment

### Quick Deploy

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
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

4. **Update OAuth Callback**
   - Railway Variables: `OAUTH_REDIRECT_URL=https://your-app.up.railway.app/auth/callback`
   - GitHub OAuth App: Update callback URL to same

5. **Configure OMI**
   - Use your Railway URLs in OMI app settings

### Railway Environment Variables

Add these in Railway dashboard:

```
GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET
OPENAI_API_KEY
OAUTH_REDIRECT_URL=https://your-app.up.railway.app/auth/callback
APP_HOST=0.0.0.0
APP_PORT=8000
```

## 🧪 Testing

### Web Interface

Visit `https://your-app.up.railway.app/test` to:
- Authenticate your GitHub account
- Test voice commands by typing
- See real-time logs
- Verify issues are being created

### With OMI Device

1. Configure webhook URLs in OMI Developer Settings
2. Enable the integration
3. Authenticate GitHub and select repository
4. Say: "Feedback Post, the app crashes when I upload images..."
5. Continue describing the problem naturally
6. Wait for AI processing (silent)
7. Get notification with issue link! 🎉

## 🧠 AI Processing

The app uses OpenAI for intelligent issue generation:

1. **Collection** - Gathers 5 segments (~15-20 seconds) for detailed context
2. **Title Generation** - Creates concise, descriptive title
3. **Description Formatting** - Structures problem statement professionally
4. **Cleanup** - Removes filler words, fixes grammar, adds proper formatting

**Example Transformation:**

```
Input (5 segments):
"the app keeps crashing when I um try to upload photos 
it happens every single time on my iPhone 14 like 
the app just freezes for a second and then 
it completely closes and this started happening 
after the latest update yesterday"

AI Output:
Title: "App crashes when uploading photos on iPhone 14"

Description:
The app consistently crashes during photo uploads. When attempting to 
upload a photo, the app freezes briefly and then closes completely. 
This issue occurs every time on iPhone 14 and started after the latest 
update.
```

## 📊 How Segments Work

**OMI sends transcripts in segments** as you speak. The app:
- ✅ Detects "Feedback Post" trigger
- ✅ Collects exactly 5 segments
- ✅ Silent during collection (no spam)
- ✅ AI processes all 5 together
- ✅ One notification on completion

**Why 5 segments?**
- Allows detailed problem description
- Captures ~15-20 seconds of speech
- Gives context for better issue formatting
- AI has full information for title/description generation

## 📱 Repository Management

### Changing Target Repository

1. Visit app homepage: `https://your-app.up.railway.app/?uid=<your_uid>`
2. Select new repository from dropdown
3. Click "Save Repository"
4. Future issues will go to the new repo!

### Refreshing Repository List

Click "Refresh Repos" to:
- Fetch latest list from GitHub
- Include newly created repositories
- Update repository access permissions

## 🔐 Security & Privacy

- ✅ OAuth 2.0 authentication (no password storage)
- ✅ Tokens stored securely with file persistence
- ✅ Per-user token isolation
- ✅ HTTPS enforced in production
- ✅ State parameter for CSRF protection
- ✅ Secure scope: only `repo` access

## 🐛 Troubleshooting

### "User not authenticated"
- Complete GitHub OAuth flow
- Check Railway logs for auth errors
- Re-authenticate if needed

### "No repository selected"
- Visit app homepage
- Select a repository from the dropdown
- Click "Save Repository"

### "Issue not creating"
- Check Railway logs for errors
- Verify repository exists and you have access
- Ensure OAuth app has correct permissions
- Check GitHub API rate limits

### "Repository not in list"
- Click "Refresh Repos" on homepage
- Ensure you have push access to the repository
- Check GitHub OAuth app permissions

### "Railway deployment fails"
- Verify all environment variables are set
- Check build logs for specific errors
- Ensure `OAUTH_REDIRECT_URL` matches GitHub OAuth app

## 📁 Project Structure

```
github/
├── main.py                  # FastAPI application with mobile-first UI
├── github_client.py         # GitHub API integration
├── issue_detector.py        # AI-powered issue detection & generation
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
| `/` | GET | Homepage with repo selection (mobile-first) |
| `/auth` | GET | Start GitHub OAuth flow |
| `/auth/callback` | GET | OAuth callback handler |
| `/setup-completed` | GET | Check if user authenticated & repo selected |
| `/webhook` | POST | Real-time transcript processor |
| `/update-repo` | POST | Update selected repository |
| `/refresh-repos` | POST | Refresh repository list |
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
- **GitHub API**: [docs.github.com/rest](https://docs.github.com/rest)

## 🎉 Credits

Built for the [OMI](https://omi.me) ecosystem.

- **OMI Team** - Amazing wearable AI platform
- **GitHub** - Issue tracking and collaboration
- **OpenAI** - Intelligent text processing

---

**Made with ❤️ for voice-first development workflows**

**Features:**
- 🎤 Voice-activated issue creation
- 🧠 AI-powered title & description generation
- 📱 Mobile-first repository management
- 🔐 Secure GitHub OAuth integration
- ⚡ Real-time processing with Railway deployment

