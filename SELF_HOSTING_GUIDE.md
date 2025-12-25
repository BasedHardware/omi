# OMI Self-Hosting Complete Guide

A comprehensive step-by-step guide to self-host OMI with your Limitless pendant on Windows + iPhone.

## Overview

This guide will walk you through:
- Setting up all required cloud services (free tiers available)
- Installing prerequisites on Windows
- Configuring and running the backend locally
- Building the iOS app to connect to your backend
- Connecting your Limitless pendant

**Estimated Time**: 3-4 hours (first time)  
**Estimated Cost**: $0-10/month (with free tiers)

---

## Phase 1: Create Required Accounts (30 mins)

Before writing any code, set up these free/trial accounts:

### 1.1 Google Cloud / Firebase (Required)

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Add project" or select existing project
3. Enter project name (e.g., "omi-self-hosted")
4. Enable Google Analytics (optional)
5. Click "Create project"
6. Wait for project creation
7. **Note your Project ID** (visible in project settings)

**Enable Firestore:**
1. In Firebase Console, go to "Firestore Database"
2. Click "Create database"
3. Start in "test mode" (we'll configure security later)
4. Choose a location (closest to you)
5. Click "Enable"

### 1.2 Deepgram (Speech-to-Text)

1. Sign up at [console.deepgram.com](https://console.deepgram.com/)
2. Verify your email
3. Go to "API Keys" section
4. Click "Create New API Key"
5. Name it "OMI Self-Hosted"
6. **Copy and save your API Key** (starts with a long string)
7. Free tier includes $200 credit

### 1.3 OpenAI (AI Processing)

1. Sign up at [platform.openai.com](https://platform.openai.com/)
2. Add payment method (required even for free tier)
3. Go to "API Keys" section
4. Click "Create new secret key"
5. Name it "OMI Self-Hosted"
6. **Copy and save your API Key** (starts with `sk-`)
7. Free tier includes $5 credit

### 1.4 Upstash (Redis)

1. Sign up at [console.upstash.com](https://console.upstash.com/)
2. Click "Create Database"
3. Name it "omi-redis"
4. Choose "Global" region (or closest to you)
5. Select "Free" tier
6. Click "Create"
7. **Copy and save:**
   - `REDIS_DB_HOST` (e.g., `omi-redis-12345.upstash.io`)
   - `REDIS_DB_PORT` (usually `6379`)
   - `REDIS_DB_PASSWORD` (long password string)

### 1.5 Pinecone (Vector Database)

1. Sign up at [app.pinecone.io](https://app.pinecone.io/)
2. Verify your email
3. Go to "Indexes" section
4. Click "Create Index"
5. Configure:
   - **Name**: `omi-vectors`
   - **Dimensions**: `1536` (for OpenAI embeddings)
   - **Metric**: `cosine`
   - **Pod Type**: `s1.x1` (free tier)
6. Click "Create Index"
7. Go to "API Keys" section
8. **Copy and save your API Key**

### 1.6 ngrok (Tunneling)

1. Sign up at [ngrok.com](https://ngrok.com/)
2. Verify your email
3. Go to "Getting Started" → "Your Authtoken"
4. **Copy your auth token** (you'll use this in Phase 2)
5. Go to "Cloud Edge" → "Domains"
6. If you have a free static domain, **note the domain name**
   - Format: `something.ngrok-free.app`
   - If you don't have one, you can use dynamic URLs (less convenient)

---

## Phase 2: Install Prerequisites (20 mins)

### 2.1 Windows Package Manager (Chocolatey)

Open PowerShell as **Administrator**:

```powershell
# Check if Chocolatey is already installed
choco --version

# If not installed, run this:
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Close and reopen PowerShell after installation
```

### 2.2 Install Required Software

```powershell
# Install all prerequisites
choco install python git ffmpeg gcloudsdk nodejs -y

# If any fail, install individually:
# choco install python -y
# choco install git -y
# choco install ffmpeg -y
# choco install gcloudsdk -y
# choco install nodejs -y
```

### 2.3 Install ngrok

```powershell
choco install ngrok -y

# Configure ngrok with your auth token
ngrok config add-authtoken YOUR_NGROK_TOKEN_HERE
```

### 2.4 Verify Installations

```powershell
python --version   # Should show 3.8 or higher
git --version
ffmpeg -version
gcloud --version
ngrok version
node --version
```

**If any commands fail:**
- Close and reopen PowerShell
- Check if the programs are in your PATH
- Restart your computer if needed

---

## Phase 3: Configure Google Cloud (15 mins)

### 3.1 Authenticate with Google Cloud

```powershell
# Login to Google Cloud
gcloud auth login

# Set your project (replace with your Project ID from Phase 1.1)
gcloud config set project YOUR_PROJECT_ID

# Set up application default credentials
gcloud auth application-default login --project YOUR_PROJECT_ID
```

This will open a browser window for authentication. After logging in, credentials will be saved automatically.

### 3.2 Enable Required APIs

Go to [Google Cloud Console API Library](https://console.cloud.google.com/apis/library) and enable:

1. **Cloud Resource Manager API**
   - Search for "Cloud Resource Manager API"
   - Click "Enable"

2. **Firebase Management API**
   - Search for "Firebase Management API"
   - Click "Enable"

3. **Cloud Firestore API**
   - Search for "Cloud Firestore API"
   - Click "Enable"

**Note**: These APIs may take a few minutes to enable.

### 3.3 Create Firestore Indexes

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project
3. Go to "Firestore Database" → "Indexes"
4. Click "Create Index"

**Create first index:**
- Collection ID: `dev_api_keys`
- Fields:
  - `user_id` - Ascending
  - `created_at` - Descending
- Click "Create"

**Create second index:**
- Collection ID: `mcp_api_keys`
- Fields:
  - `user_id` - Ascending
  - `created_at` - Descending
- Click "Create"

**Note**: Index creation may take a few minutes.

---

## Phase 4: Set Up Backend (30 mins)

### 4.1 Navigate to Backend Directory

```powershell
cd C:\Users\dotso\OneDrive\Documents\GitHub\omi\backend
```

### 4.2 Create Virtual Environment

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# You should see (venv) in your prompt
```

**To deactivate later**: `deactivate`

### 4.3 Install Python Dependencies

```powershell
# Make sure venv is activated (you should see (venv))
pip install --upgrade pip
pip install -r requirements.txt
```

**This may take 10-15 minutes** - grab a coffee! ☕

### 4.4 Create Environment File

Create a file named `.env` in the `backend` directory:

```env
# Required API Keys
OPENAI_API_KEY=sk-your-openai-key-here
DEEPGRAM_API_KEY=your-deepgram-key-here
ADMIN_KEY=your-secure-admin-key-123

# Redis (Upstash) - Replace with your values from Phase 1.4
REDIS_DB_HOST=your-redis-host.upstash.io
REDIS_DB_PORT=6379
REDIS_DB_PASSWORD=your-redis-password-here

# Pinecone - Replace with your values from Phase 1.5
PINECONE_API_KEY=your-pinecone-key-here
PINECONE_INDEX_NAME=omi-vectors

# Firebase (auto-configured via gcloud auth)
# SERVICE_ACCOUNT_JSON is optional if using gcloud auth
# If you want to use service account JSON instead, uncomment and add:
# SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

**Important**: Replace all placeholder values with your actual keys from Phase 1!

### 4.5 Start ngrok Tunnel (Terminal 1)

Open a **new PowerShell window**:

```powershell
# Start ngrok tunnel
ngrok http --domain=YOUR_DOMAIN.ngrok-free.app 8000

# If you don't have a static domain, use:
# ngrok http 8000
# Then copy the HTTPS URL it provides (e.g., https://abc123.ngrok-free.app)
```

**Keep this window open** - ngrok needs to keep running.

**Note the ngrok URL** - you'll need it for the app configuration.

### 4.6 Start Backend Server (Terminal 2)

Open a **new PowerShell window**:

```powershell
# Navigate to backend directory
cd C:\Users\dotso\OneDrive\Documents\GitHub\omi\backend

# Activate virtual environment
.\venv\Scripts\activate

# Start the backend server
uvicorn main:app --reload --env-file .env --host 0.0.0.0 --port 8000
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

**Keep this window open** - the backend needs to keep running.

### 4.7 Verify Backend is Working

1. Open your browser
2. Go to: `https://YOUR_NGROK_DOMAIN.ngrok-free.app/docs`
3. You should see the FastAPI documentation (Swagger UI)
4. Try clicking "GET /" to test the root endpoint

**If you see the docs page**: ✅ Backend is working!  
**If you get an error**: Check the backend terminal for error messages.

### 4.8 Troubleshooting Backend Issues

**If backend won't start:**
- Check all API keys in `.env` are correct
- Ensure virtual environment is activated
- Check Python version: `python --version` (should be 3.8+)
- Look at error messages in terminal

**If ngrok shows "tunnel not found":**
- Verify your auth token is set: `ngrok config check`
- Check domain name is correct
- Ensure port 8000 matches backend port

**If you see SSL/model download errors:**
- See Phase 4.9 below

### 4.9 Fix SSL Issues (If Needed)

If you get errors about "no internet connection" or SSL issues:

1. Edit `backend/utils/stt/vad.py`
2. Add these lines after the import statements:

```python
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
```

3. Save and restart the backend

---

## Phase 5: Build iOS App (45 mins)

### 5.1 Prerequisites for iOS

**Important**: iOS builds require macOS with Xcode. You have two options:

**Option A: Use a Mac** (recommended)
- Physical Mac with Xcode installed
- OR Mac cloud service (MacStadium, AWS Mac instances)

**Option B: Use Android Instead** (if no Mac available)
- Android Studio installed on Windows
- Android device or emulator
- See section 5.5 below

### 5.2 Build iOS App (on Mac)

```bash
# Navigate to app directory
cd app

# Run setup script
bash setup.sh ios

# This will:
# - Install Flutter dependencies
# - Set up Firebase configuration
# - Configure the app for development
# - Build and run the app
```

### 5.3 Configure Backend URL

Edit `app/.dev.env` file:

```env
API_BASE_URL=https://YOUR_NGROK_DOMAIN.ngrok-free.app
USE_WEB_AUTH=true
USE_AUTH_CUSTOM_TOKEN=true
```

**Important**: Use your ngrok HTTPS URL from Phase 4.5!

### 5.4 Rebuild App with New Configuration

```bash
cd app

# Clean previous build
flutter clean

# Get dependencies
flutter pub get

# Generate code
dart run build_runner build

# Run on connected iPhone
flutter run --flavor dev
```

### 5.5 Alternative: Build Android App (Windows)

If you don't have a Mac, you can build for Android:

```powershell
cd app

# Run Android setup
bash setup.sh android

# Edit app/.dev.env with your ngrok URL
# (same as iOS instructions above)

# Rebuild
flutter clean
flutter pub get
dart run build_runner build
flutter run --flavor dev
```

**Note**: You'll need Android Studio and an Android device/emulator.

---

## Phase 6: Connect Limitless Pendant (10 mins)

### 6.1 Turn On Your Pendant

1. Press and hold the button on your Limitless pendant
2. Wait for LED to light up (usually blue or green)
3. Keep it powered on

### 6.2 Open OMI App

1. Launch your self-hosted OMI app on your iPhone
2. Complete initial setup/onboarding if prompted
3. Sign in or create account (uses Firebase auth)

### 6.3 Pair Your Pendant

1. In the app, go to **Settings** → **Devices**
   - OR if first time: **Onboarding** → **Find Device**
2. Tap **"Scan for Devices"** or **"Add Device"**
3. Wait for scan to complete
4. Look for your pendant in the list:
   - Name should contain "limitless" or "pendant"
   - Shows signal strength (RSSI)
5. Tap on your pendant to connect
6. Wait for connection:
   - App will sync device time
   - Enable data streaming
   - Initialize connection
   - Should show "Connected" status

### 6.4 Test Features

**Real-time Transcription:**
1. With pendant connected, go to Capture/Home screen
2. Start speaking
3. You should see real-time transcription appear
4. Check your backend terminal - you should see API requests

**Offline Recording Sync:**
1. Disconnect from app (or turn off phone Bluetooth)
2. Use pendant to record (long press to start/stop)
3. Reconnect to app
4. Look for "Sync your recordings" card
5. Tap "Sync Now"
6. Wait for offline recordings to download

**Button Controls:**
- **Double press**: Pause/Resume conversation
- **Long press**: Device-side recording start/stop
- **Short press**: Currently not mapped (can be customized)

### 6.5 Verify Backend Connection

Check your backend terminal - you should see:
- WebSocket connections
- Transcription requests
- Audio data being processed

If you see errors, check:
- ngrok is still running
- Backend is still running
- `API_BASE_URL` in `.dev.env` is correct

---

## Architecture Overview

```
┌─────────────────┐
│ Limitless       │
│ Pendant         │
│ (Bluetooth LE)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Your iPhone     │
│ OMI App         │
│ (Self-Built)    │
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│ ngrok Tunnel    │
│ (Public URL)    │
└────────┬────────┘
         │ localhost:8000
         ▼
┌─────────────────┐
│ Your Windows PC │
│ FastAPI Backend │
│ (Local)         │
└────────┬────────┘
         │
         ├──► Deepgram (STT)
         ├──► OpenAI (AI)
         ├──► Firebase (Auth)
         ├──► Pinecone (Vectors)
         └──► Upstash Redis (Cache)
```

---

## Daily Usage

### Starting Your Self-Hosted Setup

**Every time you want to use OMI:**

1. **Start ngrok** (Terminal 1):
   ```powershell
   ngrok http --domain=YOUR_DOMAIN.ngrok-free.app 8000
   ```

2. **Start backend** (Terminal 2):
   ```powershell
   cd backend
   .\venv\Scripts\activate
   uvicorn main:app --reload --env-file .env --host 0.0.0.0 --port 8000
   ```

3. **Open app** on iPhone and connect pendant

### Stopping Your Setup

1. Press `Ctrl+C` in backend terminal
2. Press `Ctrl+C` in ngrok terminal
3. Deactivate venv: `deactivate`

---

## Troubleshooting

### Backend won't start
- ✅ Check all API keys in `.env` are correct
- ✅ Ensure virtual environment is activated (`(venv)` in prompt)
- ✅ Check Python version: `python --version` (should be 3.8+)
- ✅ Look at error messages in terminal
- ✅ Verify Firebase authentication: `gcloud auth list`

### ngrok connection issues
- ✅ Verify auth token: `ngrok config check`
- ✅ Check domain name matches your ngrok account
- ✅ Ensure port 8000 matches backend port
- ✅ Try restarting ngrok

### App can't reach backend
- ✅ Verify ngrok is running (check Terminal 1)
- ✅ Check backend is running (check Terminal 2)
- ✅ Verify `API_BASE_URL` in `app/.dev.env` matches ngrok URL
- ✅ Rebuild app after changing `.dev.env`: `flutter clean && flutter pub get`
- ✅ Check ngrok URL is HTTPS (not HTTP)

### Pendant won't pair
- ✅ Ensure Bluetooth is enabled on iPhone
- ✅ Restart pendant (hold button for 10 seconds)
- ✅ Restart app
- ✅ Forget device in iPhone Bluetooth settings, then retry
- ✅ Check pendant battery level

### No transcription appearing
- ✅ Verify backend is receiving requests (check backend terminal)
- ✅ Check Deepgram API key is correct in `.env`
- ✅ Verify ngrok tunnel is active
- ✅ Check app has microphone permissions

### Firebase authentication errors
- ✅ Verify `gcloud auth application-default login` completed
- ✅ Check project ID is correct: `gcloud config get-value project`
- ✅ Ensure Firestore indexes are created (Phase 3.3)
- ✅ Verify APIs are enabled (Phase 3.2)

---

## Cost Estimates (Monthly)

| Service | Free Tier | Paid Estimate (Light Use) |
|---------|-----------|---------------------------|
| Deepgram | $200 credit | ~$0.25/hour of audio |
| OpenAI | $5 credit | ~$0.01/request |
| Upstash Redis | 10K commands/day | $0+ |
| Pinecone | 1 index free | $0+ |
| Firebase | Generous free tier | $0+ |
| ngrok | 1 static domain free | $0+ |

**Estimated cost for light use: $0-10/month**

**For heavy use** (many hours of transcription):
- Deepgram: ~$0.25/hour
- OpenAI: ~$0.01-0.10 per conversation
- Total: $10-50/month depending on usage

---

## What You'll Learn

By completing this guide, you'll gain experience with:

1. **Backend Development**
   - FastAPI framework
   - Python async programming
   - REST API design
   - WebSocket connections

2. **Cloud Services**
   - Firebase Authentication & Firestore
   - Redis caching
   - Vector databases (Pinecone)
   - Speech-to-text APIs (Deepgram)
   - LLM APIs (OpenAI)

3. **Mobile Development**
   - Flutter/Dart
   - Bluetooth Low Energy (BLE)
   - Mobile app architecture

4. **DevOps**
   - Environment management
   - ngrok tunneling
   - Local development setup
   - Service integration

5. **AI Integration**
   - Real-time speech-to-text
   - LLM integration
   - Vector embeddings
   - Conversation processing

---

## Next Steps

After getting everything working:

1. **Explore the codebase**
   - Read `backend/main.py` to understand API structure
   - Check `app/lib/services/devices/limitless_connection.dart` for pendant protocol
   - Explore routers in `backend/routers/` to see available endpoints

2. **Customize your setup**
   - Modify transcription settings
   - Add custom features
   - Experiment with different STT providers
   - Customize button mappings

3. **Contribute back**
   - Report bugs
   - Suggest improvements
   - Submit pull requests
   - Share your learnings

4. **Scale up** (optional)
   - Deploy backend to cloud (AWS, GCP, Azure)
   - Set up CI/CD
   - Add monitoring/logging
   - Optimize performance

---

## Additional Resources

- **OMI Documentation**: [https://docs.omi.me/](https://docs.omi.me/)
- **Backend Setup Docs**: [https://docs.omi.me/doc/developer/backend/Backend_Setup](https://docs.omi.me/doc/developer/backend/Backend_Setup)
- **Discord Community**: [http://discord.omi.me](http://discord.omi.me)
- **GitHub Issues**: [https://github.com/BasedHardware/Omi/issues](https://github.com/BasedHardware/Omi/issues)

---

## Quick Reference Commands

### Backend
```powershell
# Activate venv
cd backend
.\venv\Scripts\activate

# Start backend
uvicorn main:app --reload --env-file .env --host 0.0.0.0 --port 8000

# Deactivate venv
deactivate
```

### ngrok
```powershell
# Start tunnel
ngrok http --domain=YOUR_DOMAIN.ngrok-free.app 8000

# Check status
ngrok config check
```

### App
```bash
# Clean and rebuild
cd app
flutter clean
flutter pub get
dart run build_runner build
flutter run --flavor dev
```

---

**Congratulations!** You now have a fully self-hosted OMI setup with your Limitless pendant! 🎉

