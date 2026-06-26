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

## Local Knowledge Graph — off-thread write worker

Large graphs (500+ nodes) previously blocked the Electron main thread for 1–3 s during
the synchronous `DELETE + INSERT` replace transaction, freezing IPC (chat responses, KG
reads) for that window.

### What changed

| File | Change |
|---|---|
| `src/main/ipc/kgWriteQueue.ts` | `KgWriteQueue` class — worker lifecycle, coalescing queue, Promise-based waiters |
| `src/main/ipc/kgWorker.ts` | Worker thread — own WAL connection, prepared statements, runs the replace transaction |
| `src/main/ipc/kg.ts` | Delegates to `KgWriteQueue`; `kg:saveGraph` is now awaitable |
| `src/main/ipc/db.ts` | WAL mode unconditional; `synchronous = NORMAL` scoped to worker connection only |
| `electron.vite.config.ts` | Second Rollup entry emits `out/main/kgWorker.js` |
| `electron-builder.yml` | `kgWorker.js` added to `asarUnpack` for packaged builds |

### How it works

```
renderer                  main thread                   worker thread
   │                           │                              │
   │  await kgSaveGraph(graph) │                              │
   │──────────────────────────▶│                              │
   │                           │  postMessage({type:'replace'})
   │                           │─────────────────────────────▶│
   │                           │  (main thread free for IPC)  │
   │                           │                              │ DELETE+INSERT
   │                           │  {type:'done'}               │ (WAL write lock)
   │                           │◀─────────────────────────────│
   │  Promise resolves         │                              │
   │◀──────────────────────────│                              │
```

- **At most one write runs at a time.** Subsequent `kgSaveGraph` calls while a write is
  in flight are coalesced — only the latest graph is kept (last-write-wins). All callers
  waiting in the pending window resolve together when the next write commits.
- **`kg:saveGraph` is fully awaitable.** The IPC handler returns the `KgWriteQueue`
  promise directly, so `await window.omi.kgSaveGraph(graph)` resolves only after the
  worker posts `{type:'done'}` and rejects on `{type:'error'}`, worker crash, or missing
  worker file. No silent drops.
- **Reads are never blocked.** WAL mode lets the main thread read `omi.db` while the
  worker holds the write lock. Empty-query reads are served from an in-memory snapshot
  (the last successfully written graph) and bypass SQLite entirely.
- **Durability.** The worker connection uses `synchronous = NORMAL` (acceptable for a
  derived KG cache). The main `get()` connection retains the default `FULL` sync so
  non-KG tables (`local_conversation`, `rewind_frames`, etc.) are safe on hard power-loss.

### Test coverage (`kgWriteQueue.test.ts`)

- Single round-trip: resolves after `done`, snapshot populated only then
- Coalescing: 3 rapid enqueues → only latest dispatched, all callers resolve
- Sequential saves
- `{type:'error'}` worker message → promise rejects
- Worker thread crash (`error` event) → active caller rejected, pending graph retried on fresh worker
- Factory throw (e.g. `kgWorker.js` missing) → all waiters rejected, queue drained
- Snapshot unchanged after crash or protocol error
