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
