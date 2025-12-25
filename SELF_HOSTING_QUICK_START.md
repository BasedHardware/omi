# OMI Self-Hosting Quick Start

A condensed version of the full guide for quick reference.

## Prerequisites Checklist

- [ ] Python 3.8+ installed
- [ ] Git installed
- [ ] ffmpeg installed
- [ ] Google Cloud SDK installed
- [ ] ngrok installed and configured
- [ ] All cloud accounts created (see Phase 1 in full guide)

## Quick Setup Commands

### 1. Backend Setup
```powershell
cd backend

# Run automated setup
.\..\scripts\setup_backend.ps1

# Or manual setup:
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
Copy-Item env.template .env
# Edit .env with your API keys
```

### 2. Start Services

**Terminal 1 - ngrok:**
```powershell
ngrok http --domain=YOUR_DOMAIN.ngrok-free.app 8000
```

**Terminal 2 - Backend:**
```powershell
cd backend
.\venv\Scripts\activate
uvicorn main:app --reload --env-file .env --host 0.0.0.0 --port 8000
```

### 3. Build App
```bash
cd app
# Edit app/.dev.env with your ngrok URL
flutter clean
flutter pub get
dart run build_runner build
flutter run --flavor dev
```

### 4. Verify Setup
```powershell
cd backend
.\..\scripts\verify_backend_setup.ps1
```

## Required API Keys

Fill these in your `backend/.env`:

- `OPENAI_API_KEY` - From platform.openai.com
- `DEEPGRAM_API_KEY` - From console.deepgram.com
- `REDIS_DB_HOST` - From Upstash console
- `REDIS_DB_PASSWORD` - From Upstash console
- `PINECONE_API_KEY` - From app.pinecone.io
- `PINECONE_INDEX_NAME` - Your Pinecone index name
- `ADMIN_KEY` - Any secure string

## Troubleshooting

**Backend won't start?**
- Check `.env` has all keys filled
- Verify venv is activated
- Check Python version: `python --version`

**App can't connect?**
- Verify ngrok is running
- Check `API_BASE_URL` in `app/.dev.env`
- Rebuild app after changing env

**Need help?**
- See full guide: `SELF_HOSTING_GUIDE.md`
- Discord: http://discord.omi.me

