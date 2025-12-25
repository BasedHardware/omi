# Environment Files Guide

This document explains the purpose of each `.env.template` and `.env.example` file in the OMI project.

## Overview

Each component in the OMI project has its own environment configuration file. **These are NOT duplicates** - each serves a different service/platform.

## Backend Services

### `backend/env.template`
**Purpose**: Main FastAPI backend server  
**Copy command**: `cp env.template .env`  
**Key variables**:
- OpenAI, Deepgram API keys
- Redis (Upstash) configuration
- Pinecone vector database
- Firebase/Firestore
- Optional: Stripe, OAuth providers, Hume AI

**Documentation**: See `SELF_HOSTING_GUIDE.md` for detailed setup

### `backend/pusher/.env.template`
**Purpose**: Pusher microservice (real-time notifications)  
**Key variables**:
- SERVICE_ACCOUNT_JSON

## Mobile & Desktop Apps

### `app/.env.template`
**Purpose**: Flutter mobile app (iOS/Android)  
**Copy command**: `cp .env.template .dev.env` and `cp .env.template .prod.env`  
**Key variables**:
- OPENAI_API_KEY
- API_BASE_URL (points to backend)
- GOOGLE_MAPS_API_KEY
- Google OAuth credentials
- USE_WEB_AUTH, USE_AUTH_CUSTOM_TOKEN

### `omiGlass/.env.template`
**Purpose**: OmiGlass app (Expo/React Native)  
**Key variables**:
- EXPO_PUBLIC_GROQ_API_KEY
- EXPO_PUBLIC_OLLAMA_API_URL
- EXPO_PUBLIC_OPENAI_API_KEY

## Web Frontend

### `web/frontend/.env.template`
**Purpose**: Next.js web application  
**Copy command**: `cp .env.template .env.local`  
**Key variables**:
- Firebase configuration (NEXT_PUBLIC_FIREBASE_*)
- Redis configuration
- Algolia search (NEXT_PUBLIC_ALGOLIA_*)
- Gleap customer support
- API_URL (points to backend)

## MCP Server

### `mcp/.env.template`
**Purpose**: Model Context Protocol server  
**Key variables**:
- OMI_API_BASE_URL
- OMI_API_KEY

## Plugins

### `plugins/hume-ai/.env.example`
**Purpose**: Hume AI emotion analysis plugin  
**Key variables**:
- HUME_API_KEY
- OMI_APP_ID, OMI_API_KEY
- EMOTION_NOTIFICATION_CONFIG
- Deepgram, OpenAI, Firestore (for plugin operation)

### `plugins/apps-js/.env.example`
**Purpose**: JavaScript plugins (Node.js)  
**Key variables**:
- OPENAI_API_KEY
- Upstash Redis
- JWT_SECRET
- Google OAuth
- Supabase
- OMI_APP_ID, OMI_APP_SECRET
- DECK_APP_ID, SLIDESGPT_API_KEY

### `plugins/example/.env.template`
**Purpose**: Example plugin template  
**Key variables**:
- OPENAI_API_KEY
- Redis configuration
- Various API keys (AskNews, Groq, MultiOn, Mem0, Notion)
- WORKFLOW_API_KEY
- API_BASE_URL

### `plugins/example/notifications/memorii/.env`
**Purpose**: Example notification plugin  
**Key variables**:
- OPENAI_API_KEY

## Git Configuration

The `.gitignore` is configured to:
- ✅ **Ignore** all `.env` files (your actual credentials)
- ✅ **Track** all `.env.template` and `.env.example` files (templates only)

```gitignore
*.env
.env*
!.env.template
!.env.example
```

## Security Best Practices

1. **Never commit actual `.env` files** - they contain your real API keys
2. **Only commit template files** - with placeholder values
3. **Template files should have**:
   - Placeholder values (e.g., `your-api-key-here`)
   - Comments explaining where to get each key
   - Examples for complex configurations

## Quick Reference

| Component | Template File | Actual Config File | Platform |
|-----------|--------------|-------------------|----------|
| Backend API | `backend/env.template` | `backend/.env` | Python/FastAPI |
| Pusher Service | `backend/pusher/.env.template` | `backend/pusher/.env` | Python |
| Mobile App | `app/.env.template` | `app/.dev.env`, `app/.prod.env` | Flutter/Dart |
| Web Frontend | `web/frontend/.env.template` | `web/frontend/.env.local` | Next.js |
| MCP Server | `mcp/.env.template` | `mcp/.env` | Python |
| OmiGlass | `omiGlass/.env.template` | `omiGlass/.env` | Expo/React Native |
| Hume Plugin | `plugins/hume-ai/.env.example` | `plugins/hume-ai/.env` | Python |
| JS Plugins | `plugins/apps-js/.env.example` | `plugins/apps-js/.env` | Node.js |

## Setup Workflow

1. Navigate to the component directory
2. Copy the template: `cp env.template .env` (or `.env.example` → `.env`)
3. Edit `.env` with your actual API keys
4. Never commit the `.env` file

## Common Variables Across Components

- **OPENAI_API_KEY**: Used by backend, apps, plugins
- **API_BASE_URL**: Points to backend (used by frontend/apps)
- **Redis**: Used by backend and web frontend
- **Firebase/Firestore**: Used by backend and web frontend

---

**Last Updated**: 2025-12-25  
**Related Docs**: `SELF_HOSTING_GUIDE.md`, `SELF_HOSTING_QUICK_START.md`

