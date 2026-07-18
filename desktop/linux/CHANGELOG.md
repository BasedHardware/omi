# Changelog — Omi Linux Desktop App

## v1.1.0 (June 2026)

### New Features

#### Voice Agent with Deepgram
- Full STT + LLM + TTS pipeline via Deepgram Voice Agent
- Real-time voice conversations with AI assistant
- Personality system via `soul.md` — customize your agent's identity, tone, and behavior
- Function calling: web search, calculator, reminders
- Sentiment analysis on transcriptions (nova-3 model)
- Auto-saves transcripts to SQLite with summaries and tasks

#### Local LLM Support (Ollama)
- Connect local LLMs via Ollama for fully offline voice agent
- OpenAI-compatible API endpoint support
- Configurable model and endpoint in Settings
- Health check button to verify Omi connection

#### Omi Device Bluetooth Support
- Connect Omi wearable via BLE (Bluetooth Low Energy)
- Streams audio directly from device to voice agent
- Codec conversion (PCM16/Opus) for compatibility
- Battery level and firmware version display
- Auto-routes to Deepgram (default) or Omi cloud (with subscription)

#### Auto-Summarization
- Conversations auto-summarize on save via Gemini
- Extracts summary, tasks, and key points
- Tasks shown in conversation list with badge count
- Full task list with checkboxes in conversation detail

#### Linux OCR Support
- Tesseract OCR fallback for Linux/NixOS
- Platform-aware: uses win-ocr-helper on Windows, Tesseract on Linux
- Screen capture works on Wayland via WebRTCPipeWireCapturer

### UI Improvements

#### Home Page
- New recording button (mic icon) — start recording directly from Home
- New Chat button — reset conversation thread to start fresh
- Connect Omi Device button — pair BLE device from greeting screen

#### Conversation List
- Task count badge on conversations with auto-generated tasks
- Shows "2 tasks" indicator next to relevant conversations

#### Conversation Detail
- Displays auto-generated summary
- Action items with toggleable checkboxes
- Key points section

### Bug Fixes
- Fixed "New Chat" not creating fresh conversation (was reusing same ID in infinite mode)
- Fixed Ask Omi showing old conversations — now properly resets thread

### Documentation
- Screen Recording Setup Guide (`SCREEN_RECORDING_SETUP.md`)
- Linux/NixOS installation instructions
- Troubleshooting for Bluetooth, OCR, and permissions

---

## Setup Instructions

### Quick Start
```bash
# Run the app
appimage-run dist/omi-windows-1.0.0.AppImage
```

### Prerequisites

#### Deepgram API Key (required for Voice Agent)
1. Sign up at https://deepgram.com
2. Get your API key
3. Set environment variable:
```bash
export MAIN_VITE_DEEPGRAM_API_KEY="your-api-key-here"
```

#### Ollama (optional, for local LLM)
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull fredrezones55/Qwopus3.5

# Start Ollama
ollama serve
```

#### Tesseract (optional, for screen OCR on Linux)
```bash
# NixOS
nix-env -iA nixpkgs.tesseract

# Ubuntu/Debian
sudo apt install tesseract-ocr

# Arch
sudo pacman -S tesseract
```

### Bluetooth Omi Device
1. Enable Bluetooth on your computer
2. Put Omi device in pairing mode
3. Click "Connect Omi Device" on Home page or in Settings
4. Select "Omi" from the Bluetooth dialog
5. Audio automatically routes to voice agent

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Interfaces                       │
├─────────────────────────────────────────────────────────┤
│  Home Page     │  Settings      │  Conversations        │
│  - Chat bar    │  - Voice Agent │  - List with tasks    │
│  - Mic button  │  - LLM provider│  - Detail with summary│
│  - BLE connect │  - BLE device  │  - Transcripts        │
└────────┬───────┴───────┬────────┴──────────┬───────────┘
         │               │                   │
┌────────▼───────────────▼───────────────────▼───────────┐
│                    Core Libraries                        │
├─────────────────────────────────────────────────────────┤
│  deepgramAgentClient  │  omiBleClient                   │
│  - Mic/BLE capture    │  - BLE protocol                 │
│  - Agent session      │  - Audio streaming              │
│  - Transcript saving  │  - Device management            │
├─────────────────────────────────────────────────────────┤
│  summaryClient        │  conversationSummaries          │
│  - Gemini extraction  │  - localStorage persistence     │
│  - Tasks/points       │  - Auto-summary on save         │
├─────────────────────────────────────────────────────────┤
│  transcriptionClient  │  localAgent                     │
│  - Deepgram/Omi STT   │  - Context injection            │
│  - Fallback logic     │  - Knowledge graph              │
└─────────────────────────────────────────────────────────┘
         │               │                   │
┌────────▼───────────────▼───────────────────▼───────────┐
│                    Main Process                          │
├─────────────────────────────────────────────────────────┤
│  deepgramAgent.ts     │  deepgramListen.ts              │
│  - WebSocket to agent │  - WebSocket to STT             │
│  - Soul.md loader     │  - Sentiment analysis           │
│  - Conversation ctx   │  - Audio buffering              │
├─────────────────────────────────────────────────────────┤
│  ocr/helperProcess.ts │  db.ts                          │
│  - Tesseract (Linux)  │  - SQLite conversations         │
│  - win-ocr (Windows)  │  - Local storage                │
└─────────────────────────────────────────────────────────┘
         │
┌────────▼───────────────────────────────────────────────┐
│                    External Services                     │
├─────────────────────────────────────────────────────────┤
│  Deepgram          │  Gemini (via Omi proxy)            │
│  - Voice Agent     │  - Summarization                   │
│  - STT (nova-3)    │  - Context generation              │
│  - TTS (Aura)      │                                   │
│  - Sentiment       │  Omi Cloud (optional)              │
│                    │  - Memories API                    │
│                    │  - Conversations API               │
└─────────────────────────────────────────────────────────┘
```

---

## File Changes

### New Files
- `soul.md` — Agent personality definition
- `src/main/ipc/deepgramAgent.ts` — Voice Agent WebSocket
- `src/main/ipc/deepgramListen.ts` — Deepgram STT with sentiment
- `src/main/ipc/deepgramTts.ts` — Deepgram Aura TTS
- `src/main/ocr/linuxOcr.ts` — Tesseract OCR for Linux
- `src/renderer/src/lib/deepgramAgentClient.ts` — Agent client with BLE
- `src/renderer/src/lib/omiBleClient.ts` — BLE device client
- `src/renderer/src/lib/summaryClient.ts` — Transcript summarization
- `src/renderer/src/lib/conversationSummaries.ts` — Summary persistence
- `SCREEN_RECORDING_SETUP.md` — Screen recording documentation

### Modified Files
- `src/main/index.ts` — Permission handlers, IPC registration
- `src/main/ipc/db.ts` — SQLite schema
- `src/main/ocr/helperProcess.ts` — Platform-aware OCR
- `src/preload/index.ts` — IPC bridge methods
- `src/shared/types.ts` — AgentConfig, BackendSegment, OmiBridgeApi
- `src/renderer/src/pages/Home.tsx` — Recording, BLE, new chat
- `src/renderer/src/pages/Conversations.tsx` — Task badges
- `src/renderer/src/pages/ConversationDetail.tsx` — Auto-summaries
- `src/renderer/src/hooks/useRecorder.ts` — Auto-summarize on save
- `src/renderer/src/hooks/useChat.ts` — Fixed reset for new conversations
- `src/renderer/src/components/settings/tabs/GeneralTab.tsx` — LLM provider, BLE device
- `electron-builder.yml` — Extra resources for soul.md
