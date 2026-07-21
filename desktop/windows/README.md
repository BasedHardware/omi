# omi-windows

Omi for Windows — an Electron + React + TypeScript port of the Omi desktop app.

## Recommended IDE Setup

- [VSCode](https://code.visualstudio.com/) + [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) + [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode)

## Prerequisites

- Node.js 22 and pnpm 10 (run `corepack prepare pnpm@10 --activate` to select it).
- The .NET 10 SDK for OCR, screen-reading, and UI automation. The app still runs
  without it, but those native-helper features remain disabled.

## Run from source

```powershell
# 1. Enable the repository's package manager and install dependencies
corepack prepare pnpm@10 --activate
pnpm install

# 2. Create your local env file (required — the app won't start without it)
Copy-Item .env.example .env

# 3. Start the app
pnpm run dev
```

`.env` is gitignored. `.env.example` ships with Omi's **public** Firebase + PostHog
config, so after copying `.env.example` to `.env` the app runs and sign-in works with no extra
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

```powershell
# Windows
# Build both native helpers (requires the .NET 10 SDK)
pnpm run build:native-helpers

# Build an unpacked Windows app and verify both packaged helpers
pnpm run build:unpack
pnpm run verify:packaged-native-helpers

pnpm run build:win

# macOS
pnpm run build:mac

# Linux
pnpm run build:linux
```

Vite inlines the `.env` values at build time, so a packaged installer needs no `.env` —
the config is compiled into the binary.
