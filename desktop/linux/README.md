# omi-linux

A voice-first AI assistant for Linux built on [Omi](https://github.com/BasedHardware/omi) — enhanced with Deepgram Voice Agent, MCP tool integration, and a configurable personality system. Runs on **NixOS/Linux** via AppImage.

## What it does

Speak naturally and the AI listens, thinks, and responds — all through one Deepgram WebSocket. It can search the web, do math, set reminders, and summarize your conversations. Say its name to wake it up, or let it listen passively in the background.

## Features

- **Voice Agent** — Full STT + LLM + TTS pipeline via Deepgram's Voice Agent API
- **Wake Word Activation** — Agent only responds when you say its name (configurable)
- **Personality System** — Set a name, personality traits, and behavioral rules
- **MCP Tools** — Web search, calculator, time, reminders (extensible)
- **Transcript Summarizer** — Extract summaries, tasks, and key points via Gemini
- **Deepgram Transcription** — Real-time speech-to-text with audio buffering
- **NixOS/Wayland Support** — Mic permissions, PipeWire capture, AppImage build

## Quick Start

```bash
# Clone
git clone https://github.com/palontologist/omi-linux.git
cd omi-linux

# Install
pnpm install

# Configure
cp .env.example .env
# Edit .env — add your Deepgram API key:
# MAIN_VITE_DEEPGRAM_API_KEY=your_key_here

# Run in dev
pnpm run dev
```

## Build for Linux

```bash
pnpm run build:linux
```

Output: `dist/omi-windows-1.0.0.AppImage`

### Run on NixOS

```bash
appimage-run dist/omi-windows-1.0.0.AppImage
```

No FUSE needed. AppImage is extracted to `~/.cache/appimage-run/` automatically.

## Configuration

### .env

| Variable | Required | Description |
|----------|----------|-------------|
| `MAIN_VITE_DEEPGRAM_API_KEY` | Yes | Deepgram API key for STT + Voice Agent |
| `VITE_OMI_API_KEY` | No | Omi cloud sync (blank = local only) |
| `MAIN_VITE_GOOGLE_CLIENT_ID` | No | Google OAuth for Gmail/Calendar |
| `MAIN_VITE_GOOGLE_CLIENT_SECRET` | No | Google OAuth secret |

### Voice Agent (Settings > General)

- **Name** — Agent's name (default: "friend"). Say it to activate.
- **Activation** — "Say name to activate" or "Always respond"
- **Personality** — e.g. "warm, curious, sarcastic"
- **Ask when unsure** — Agent asks clarifying questions

### Voice Agent requires an LLM

The Voice Agent uses Deepgram's think provider. Configure one in your [Deepgram Dashboard](https://console.deepgram.com) under Project Settings > Voice Agent:

- OpenAI (gpt-4o-mini)
- Google (gemini-2.0-flash)
- Anthropic (claude-3-5-haiku)

## Tools

The voice agent can use these tools automatically:

| Tool | Description | Example |
|------|-------------|---------|
| `web_search` | Search DuckDuckGo | "What's the news today?" |
| `get_time` | Current date/time | "What time is it?" |
| `calculate` | Math expressions | "What's 144 * 37?" |
| `set_reminder` | Timed reminders | "Remind me to check email in 30 min" |

Tools execute locally in the Electron main process. Results are sent back to the LLM for a spoken response.

## Architecture

```
Renderer (React)          Main Process (Electron)         Deepgram
─────────────────         ──────────────────────         ─────────
Mic capture ──────────► Agent WS handler ──────────► Voice Agent API
                              │                         (STT + LLM + TTS)
                              ├──► Tool execution
                              │    (web_search, calc...)
                              │
TTS playback ◄────────── Agent audio ◄────────────── TTS audio
```

## NixOS Notes

- **No .deb/.snap** — Ruby/fpm dependency fails on NixOS. Use AppImage only.
- **Mic permissions** — Electron's `setPermissionRequestHandler` + PipeWire flags handle Wayland.
- **Disk space** — AppImage is ~168MB. Clean `~/.cache/appimage-run/` if low on space.

## Credits

- [Omi](https://github.com/BasedHardware/omi) — Original desktop app
- [Deepgram](https://deepgram.com) — Voice Agent API (STT + LLM + TTS)
- [Electron](https://electronjs.org) + [Vite](https://vitejs.dev)
