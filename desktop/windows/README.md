# omi-windows

Omi for Windows — an Electron + React + TypeScript port of the Omi desktop app.

## Recommended IDE Setup

- [VSCode](https://code.visualstudio.com/) + [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) + [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode)

## Run from source

```bash
# 1. Install dependencies
npm install

# 2. Create your local env file (required — the app won't start without it)
cp .env.example .env

# 3. Start the app
npm run dev
```

`.env` is gitignored. `.env.example` ships with Omi's **public** Firebase + PostHog
config, so after `cp .env.example .env` the app runs and sign-in works with no extra
keys to obtain.

## Authentication

- **App sign-in:** each user signs in with **their own** Google/Omi account through
  the built-in popup. The Firebase project is shared (Omi's `based-hardware`); accounts
  are individual. Nothing to configure — it works out of the box from `.env.example`.
- **Google integration** (optional Gmail/Google connect — separate from sign-in): bring
  your own credentials. Create an OAuth **Desktop app** client in the
  [Google Cloud Console](https://console.cloud.google.com/apis/credentials), then in your
  local `.env` set `MAIN_VITE_GOOGLE_CLIENT_ID`, `MAIN_VITE_GOOGLE_CLIENT_SECRET`, and
  `VITE_ENABLE_GOOGLE_INTEGRATION=1`. Keep these in your local `.env` only — never commit them.

## Optional keys

Everything below is blank in `.env.example` and safe to leave unset:

- `VITE_OMI_API_KEY` — cloud-sync recorded conversations (generate in Omi → Settings →
  Developer). Blank = recordings save locally only.
- `MAIN_VITE_GOOGLE_CLIENT_ID` / `MAIN_VITE_GOOGLE_CLIENT_SECRET` /
  `VITE_ENABLE_GOOGLE_INTEGRATION` — the Google integration above.

## Coding agents (Claude Code, OpenClaw, Hermes, Codex)

Omi can delegate tasks to external coding agents over ACP (Agent Client
Protocol). Name an agent in chat or push-to-talk — *"ask Codex to fix the
failing test in my omi repo"*, *"use Claude Code to add a readme"* — and Omi
hands the task over, streaming the agent's progress into the conversation. If
the agent you named fails to start, Omi falls back to the next connected one;
if it isn't connected at all, the reply tells you how to set it up.

- **Claude Code** ships built in (the `@zed-industries/claude-agent-acp`
  bridge, spawned as a Node child process) — no separate install. It uses your
  Claude sign-in (`claude` CLI credentials or `ANTHROPIC_API_KEY`).
- **OpenClaw / Hermes / Codex** are external CLIs you install yourself, then
  connect in **Settings → Agents** by saving a launch command
  (e.g. `openclaw acp`, `hermes acp`, `npx @agentclientprotocol/codex-acp`).
  The **Test** button runs a real ACP handshake against the command.
  Power users can instead set `OMI_OPENCLAW_ADAPTER_COMMAND` /
  `OMI_HERMES_ADAPTER_COMMAND` / `OMI_CODEX_ADAPTER_COMMAND` in the
  environment; a Settings command takes precedence when both exist.

External agents run with a minimal allowlisted environment (host secrets are
never forwarded) and never receive automatic permanent permission grants.
The working directory for a task is an explicit path in your message, else the
indexed folder matching a "in my X repo" hint, else your most recently active
indexed folder. Adapter code lives in `src/main/codingAgent/`.

## Build

```bash
# Windows
npm run build:win

# macOS
npm run build:mac

# Linux
npm run build:linux
```

Vite inlines the `.env` values at build time, so a packaged installer needs no `.env` —
the config is compiled into the binary.
