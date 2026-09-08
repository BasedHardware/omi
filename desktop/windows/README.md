# omi-windows

Omi for Windows — an Electron + React + TypeScript port of the Omi desktop app.

## Recommended IDE Setup

- [VSCode](https://code.visualstudio.com/) + [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) + [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode)

## Run from source

Requires Node 22.19+ (CI pins Node 22, matching `package.json`'s `engines.node`
range; Node 24+ breaks the jsdom test suites — see `scripts/check-node-version.mjs`).
With [nvm](https://github.com/nvm-sh/nvm) installed, `nvm use` in this directory
picks up the pinned version from `.nvmrc` automatically.

This directory is pnpm-managed — running `npm install` instead will corrupt
`package.json`/`pnpm-lock.yaml`/`pnpm-workspace.yaml` (npm doesn't understand
pnpm-workspace semantics) and leave a stray, untracked `package-lock.json`
behind. If you see unexplained diffs in those three files with no matching
commit, this is almost certainly why — `git restore` them and reinstall with
pnpm.

CI pins pnpm to major version **10**. If your system `pnpm --version` is a
different major (e.g. 8 or 11+), `.npmrc`'s `node-linker=hoisted` setting can
be silently ignored, breaking postinstall with a confusing "closure
package(s) do not resolve on disk" error — use `npx pnpm@10 <command>`
instead of downgrading a system-managed pnpm install.

```bash
# 1. Install dependencies
nvm use   # or: nvm install (first time)
pnpm install --frozen-lockfile

# 2. Create your local env file (required — the app won't start without it)
cp .env.example .env

# 3. Start the app
pnpm run dev
```

`.env` is gitignored. `.env.example` ships with Omi's **public** Firebase + PostHog
config, so after `cp .env.example .env` the app runs and sign-in works with no extra
keys to obtain.

### Linux (Wayland compositors)

On native Wayland compositors with limited XWayland support (e.g. niri),
`pnpm dev` can fail to map the main window at all — the tray icon appears but
no window does. Set `OMI_OZONE=wayland` to run under native Wayland instead
(global shortcuts and active-window detection won't work in that mode). If
the window still comes up blank rather than missing, also add
`OMI_DEV_HW_GPU=1`. See [docs/multi-worktree-dev.md](docs/multi-worktree-dev.md)
for the full dev-only environment variable reference and parallel-worktree
port/profile isolation.

`pnpm run dev` automatically unsets `ELECTRON_RUN_AS_NODE` for the spawned Electron
app. Some shell/tooling sessions leave that variable set after using Electron as a
Node runtime; if it leaks into app startup, Electron does not expose `electron.app`
and the dev app crashes before opening.

## Authentication

- **App sign-in:** each user signs in with **their own** Google or Apple/Omi account
  through the system browser. The Windows app uses the same backend-mediated OAuth
  flow as the macOS app, so provider credentials stay server-side. The Firebase project
  is shared (Omi's `based-hardware`); accounts are individual. Nothing to configure —
  it works out of the box from `.env.example`.
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

- **Claude Code** ships built in (the `@agentclientprotocol/claude-agent-acp`
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
pnpm run build:win

# macOS
pnpm run build:mac

# Linux
pnpm run build:linux
```

Vite inlines the `.env` values at build time, so a packaged installer needs no `.env` —
the config is compiled into the binary.

## Verify your changes

```bash
pnpm typecheck   # tsc, node + web configs
pnpm lint        # ESLint (blocking in CI; Prettier formatting is not)
pnpm test        # vitest, ~550 tests, runs against an Electron stub
```

## Floating bar

The always-on-top bar window has several non-obvious Windows pathologies (OS
show-fade, clip-reveal requirement, orb WebGL blink, eaten hardware clicks). Read
[docs/bar-gotchas.md](docs/bar-gotchas.md) **before** changing bar window logic or
animations — it also documents the fast verification loop (harness scripts,
`[bar-diag]` logging).

## Conversation sync

Screen-session (mic + system audio) recordings sync to the Omi cloud via
`POST /v1/conversations/from-segments` with a client-owned outbox (offline
retry, duplicate-safe). Design, outbox semantics, and the live E2E harness
(`pnpm test:e2e:conv-sync`) are documented in
[docs/conversation-sync.md](docs/conversation-sync.md).
