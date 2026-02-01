# Backend Setup

Guide for setting up the Omi backend development environment.

## Purpose

Set up the Omi backend for local development with all required services and dependencies.

## Prerequisites

- Python 3.9-3.12
- Google Cloud SDK
- Firebase project
- API keys (OpenAI, Deepgram, Pinecone, Redis, etc.)

## Setup Steps

1. **Navigate to backend directory**
   ```bash
   cd backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # macOS/Linux
   # or
   venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install PyOgg
   pip install -r requirements.txt
   ```

4. **Set up Google Cloud credentials**
   ```bash
   gcloud auth login
   gcloud config set project <project-id>
   gcloud auth application-default login
   cp ~/.config/gcloud/application_default_credentials.json ./google-credentials.json
   ```

5. **Create environment file**
   ```bash
   cp .env.template .env
   ```

6. **Configure environment variables**
   Edit `.env` and add:
   - `OPENAI_API_KEY`
   - `DEEPGRAM_API_KEY`
   - `PINECONE_API_KEY`
   - `REDIS_DB_HOST`, `REDIS_DB_PORT`, `REDIS_DB_PASSWORD`
   - `GOOGLE_APPLICATION_CREDENTIALS=./google-credentials.json`
   - And other required variables (see `.env.template`)

7. **Set up Ngrok (for local development)**
   ```bash
   ngrok http --domain=your-domain.ngrok-free.app 8000
   ```

8. **Start backend server**
   ```bash
   uvicorn main:app --reload --env-file .env --port 8000
   ```

## Verification

- Backend should be accessible at `http://localhost:8000`
- API docs at `http://localhost:8000/docs`
- WebSocket endpoint at `ws://localhost:8000/v4/listen`

## Troubleshooting

- **Module not found**: Ensure virtual environment is activated
- **Firebase errors**: Check Google credentials file path
- **Redis errors**: Redis is optional but recommended
- **API key errors**: Verify all API keys in `.env`

## Related Documentation

- Backend Setup: `docs/doc/developer/backend/Backend_Setup.mdx`
- Backend Deep Dive: `docs/doc/developer/backend/backend_deepdive.mdx`
