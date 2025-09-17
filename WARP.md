# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

Omi is the world's leading open-source AI wearable that captures conversations, provides summaries, action items, and performs actions. This repository contains multiple interconnected components that work together to provide the full Omi experience.

## Architecture

The repository follows a multi-component architecture:

- **`backend/`** - FastAPI-based Python backend serving the core API
- **`app/`** - Flutter mobile application (iOS/Android)
- **`omiGlass/`** - Expo React Native app for smart glasses hardware
- **`web/frontend/`** - Next.js web application
- **`web/personas-open-source/`** - Personas web interface
- **`mcp/`** - Model Context Protocol server for AI assistant integration
- **`omi/`** - Hardware firmware and related code
- **`plugins/`** - Integration plugins ecosystem
- **`docs/`** - Documentation site (Mintlify)

## Common Development Commands

### Backend (Python/FastAPI)
```bash
# Setup and run
cd backend
cp .env.template .env
# Configure .env with API keys (OpenAI, Deepgram, Redis, etc.)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload --env-file .env

# Code formatting
black --line-length 120 --skip-string-normalization .

# Load testing
cd testing
python load_test.py
locust -f locustfile.py
```

### Mobile App (Flutter)
```bash
# Setup
cd app
bash setup.sh ios     # or android
cd ~/.ssh; ssh-add    # Setup SSH for certificates

# Development
flutter run --flavor dev
flutter test

# Production build and deploy to iPhone
flutter build ios --flavor dev --release
ios-deploy --bundle build/ios/iphoneos/Runner.app --debug
```

### OmiGlass (Expo/React Native)
```bash
cd omiGlass
npm install  # or yarn install
cp .env.example .env
# Configure API keys (Groq, OpenAI)
ollama pull moondream:1.8b-v2-fp16

# Development
npm start    # or yarn start
expo start --web  # for web version
```

### Web Frontend (Next.js)
```bash
cd web/frontend
npm install
npm run dev          # Development server
npm run build        # Production build
npm run lint         # ESLint
npm run lint:fix     # Fix linting issues
npm run lint:format  # Prettier formatting
```

### MCP Server (Model Context Protocol)
```bash
cd mcp
cp .env.template .env
# Set OMI_API_KEY from app Settings > Developer > MCP
python -m pip install -r requirements.txt
# Use with Docker or direct Python execution
```

### Documentation
```bash
cd docs
npm i -g mintlify
mintlify dev      # Preview docs locally
```

## Testing

### Backend Testing
- Load testing scripts in `backend/testing/`
- Run load tests: `python backend/testing/load_test.py`
- Locust performance testing: `locust -f backend/testing/locustfile.py`

### Mobile App Testing
- Integration tests in `app/test_driver/`
- Run tests: `flutter test` (from app directory)

### Single Test Execution
- Backend: No specific single test runner configured (add pytest for granular testing)
- App: `flutter test test/specific_test_file.dart`

## Key Configuration Files

### Environment Setup
Each component has `.env.template` files that need to be copied to `.env`:
- `backend/.env.template` - API keys for OpenAI, Deepgram, Redis, Pinecone, etc.
- `app/.env.template` - App-specific configuration
- `omiGlass/.env.template` - Groq/OpenAI keys for AI processing
- `mcp/.env.template` - MCP server configuration

### Critical Dependencies
- **Backend**: Redis (Upstash recommended), Google Cloud Project with Firebase
- **App**: iOS/Android development environment, SSH access for certificates
- **OmiGlass**: Ollama for local AI models
- **All**: Proper API key configuration is essential

## Development Workflow

### Backend Development
1. Authenticate with Google Cloud: `gcloud auth login && gcloud config set project <project-id>`
2. Set up ngrok for local development: `ngrok http --domain=example.ngrok-free.app 8000`
3. Configure app to use local backend via `API_BASE_URL`

### Hardware Development
- Firmware in `omi/` directory for device hardware
- OmiGlass hardware assembly requires 3D printing STL files from `hardware/` folder
- Arduino IDE setup for XIAO ESP32S3 with PSRAM configuration

### Plugin Development
- Plugins system documented at: https://docs.omi.me/docs/developer/apps/Introduction/
- Community plugins tracked in `community-plugins.json`

## Important Notes

### Authentication & APIs
- Google Cloud Resource Manager, Firebase Management, and Firestore APIs must be enabled
- Pinecone vector database requires proper index configuration (1536 dimensions for OpenAI embeddings)
- Multiple AI providers supported: OpenAI, Groq, local Ollama models

### Mobile Development
- iOS requires Developer Mode enabled and proper certificate setup
- Android needs USB debugging in Developer Options
- SSH key setup critical for certificate access

### Hardware Components
- OmiGlass requires specific battery configuration (6x 150mah + 1x 250mah)
- ESP32 S3 Sense board with specific PSRAM settings
- No power switch in current design - manual wire connection required

### Production Considerations
- Backend supports self-hosting with custom `OMI_API_BASE_URL`
- Multiple deployment targets: mobile apps, web interfaces, hardware firmware
- Community contribution system with paid bounties available
