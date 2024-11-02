# Backend Setup Guide

## Prerequisites

### Required Software
- Python 3.10 or higher
- pip (Python package manager)
- git
- ffmpeg
- Google Cloud SDK
- Redis instance (e.g., [Upstash](https://upstash.com/))
- [ngrok](https://ngrok.com/) for local development

### Required Accounts
- Google Cloud Project with Firebase enabled
- OpenAI API account
- Deepgram account
- Redis instance (Upstash recommended)
- GitHub account (for API access)

## Installation Steps

### 1. Google Cloud Setup
1. Install Google Cloud SDK:
   ```bash
   brew install google-cloud-sdk   # macOS with Homebrew
   ```

2. Configure Google Cloud:
   ```bash
   gcloud auth login
   gcloud config set project <project-id>
   gcloud auth application-default login --project <project-id>
   ```
   > Replace `<project-id>` with your Google Cloud Project ID
   > This generates application_default_credentials.json in ~/.config/gcloud/

3. Enable required Google Cloud APIs:
   - Cloud Resource Manager
   - Firebase Management API
   - Cloud Storage
   - Firestore

### 2. Local Environment Setup
1. Clone the repository and navigate to backend:
   ```bash
   cd backend
   ```

2. Create Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Unix/macOS
   # or
   .venv\Scripts\activate     # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create environment file:
   ```bash
   cp .env.template .env
   ```

### 3. Configuration

1. Required Environment Variables:
   - `GOOGLE_APPLICATION_CREDENTIALS`: Path to google-credentials.json
   - `BUCKET_SPEECH_PROFILES`: GCS bucket for speech profiles
   - `BUCKET_MEMORIES_RECORDINGS`: GCS bucket for memory recordings
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `DEEPGRAM_API_KEY`: Your Deepgram API key
   - `REDIS_DB_HOST`, `REDIS_DB_PORT`, `REDIS_DB_PASSWORD`: Redis connection details
   - `ADMIN_KEY`: Set to any value for local development

2. Optional Environment Variables:
   - `BUCKET_POSTPROCESSING`: For audio post-processing
   - `BUCKET_TEMPORAL_SYNC_LOCAL`: For temporary sync files
   - `BUCKET_BACKUPS`: For backups
   - Other variables as listed in .env.template

### 4. Running the Server

1. Configure ngrok:
   ```bash
   ngrok http --domain=your-domain.ngrok-free.app 8000
   ```
   > Replace your-domain with your ngrok static domain

2. Start the server:
   ```bash
   uvicorn main:app --reload --env-file .env
   ```

### 5. Troubleshooting

If you encounter SSL certificate errors with model downloads:
```python
# Add to utils/stt/vad.py after imports
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
```

## Development Notes

- The server runs on port 8000 by default
- Use the ngrok URL in your app's environment as `API_BASE_URL`
- Required directories are created automatically on startup
- Check logs for initialization status of various services

## Additional Resources

- [Google Cloud Console](https://console.cloud.google.com)
- [Firebase Console](https://console.firebase.google.com)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Deepgram Documentation](https://developers.deepgram.com)
- [Upstash Redis Documentation](https://docs.upstash.com/redis)

