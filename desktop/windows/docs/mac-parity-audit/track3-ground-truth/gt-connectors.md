# Ground Truth: Unified Connectors Capability (Imports + Exports/MCP)

Sources read directly (not doc summaries), Mac reference frozen v0.12.72:
- `desktop/macos/Desktop/Sources/MainWindow/Pages/ConnectorImportOperations.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/ConnectorImportRunner.swift`
- `desktop/macos/Desktop/Sources/GmailReaderService.swift`
- `desktop/macos/Desktop/Sources/CalendarReaderService.swift`
- `desktop/macos/Desktop/Sources/Onboarding/OnboardingImportEvidenceService.swift`
- `desktop/macos/Desktop/Sources/MainWindow/Pages/MemoryExportDestinationSheet.swift`
- `desktop/macos/Desktop/Sources/MemoryBankConnector.swift`
- `desktop/macos/Desktop/Sources/MemoryExportService.swift`
- `desktop/macos/Desktop/Sources/MemoryExportConnectionDetector.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift` (relevant sections)
- Windows existing: `desktop/windows/src/main/ipc/memoryExport.ts`, `src/main/memoryExport/*`, `src/main/ipc/integrations.ts`, `src/main/integrations/{oauth,google,googleMap,syncState}.ts`, `src/renderer/src/components/settings/tabs/IntegrationsTab.tsx`, `src/renderer/src/lib/{memoryExtract,googleSync}.ts`
- Backend: `backend/routers/{mcp.py,x_connector.py,memories.py,google_calendar.py}`

---

## 1. IMPORTS (Mac)

### 1.1 Gmail

**Mechanism: NOT the Google API with OAuth.** Mac reads Gmail by decrypting the user's **browser cookies** (Chrome/Arc/Brave/Edge, all profiles) via a bundled Python helper (`BrowserPythonRunner` + `BrowserGoogleSession.chromiumCookiePythonSupport`), then hits Gmail's **internal, undocumented surfaces**:
- Primary: fetch `https://mail.google.com/mail/u/0/` (home page) and scrape an embedded JS data blob (`"a6jdv":[["sils",null,"..."` needle) — the "bootstrap inbox snapshot."
- Fallback: Gmail's legacy **Atom feed** `https://mail.google.com/mail/feed/atom?q=<query>` (and per-label feeds: `atom/inbox`, `atom/sent`, `atom/starred`, etc. — 13 feeds merged) for queries older than 20 days.
- Query: `"newer_than:365d"`, `maxResults: 300` (`ConnectorImportOperations.importGmail`).
- No backend proxy, no OAuth. All done locally with the signed-in browser session's cookies. Auth cookie check: `GOOGLE_AUTH_COOKIE_NAMES`.
- Failure classes (`GmailFailureClass`): `no_browser`, `not_signed_in`, `session_expired`, `decrypt_failed`, `network`, `unknown` — each mapped to an actionable user-facing message.

**Windows already has a materially different (arguably better) implementation, feature-flagged off** (`VITE_ENABLE_GOOGLE_INTEGRATION`): real **Google OAuth 2.0 PKCE loopback** flow (`src/main/integrations/oauth.ts`) against `https://oauth2.googleapis.com/token`, then genuine **Gmail REST API** reads (`src/main/integrations/google.ts`, `GMAIL_BASE = https://gmail.googleapis.com/gmail/v1/users/me`, `format=metadata`, Subject/From only, `newer_than:7d`, 25 results, incremental via `syncState.ts` processed-ID set). This is NOT a port of Mac's cookie-scraping workaround — it's a cleaner Google-approved API path already built. Recommendation for Track 6/design: prefer extending Windows' existing OAuth+API path over porting Mac's browser-cookie scraping, unless product explicitly wants "no OAuth consent screen" parity with Mac.

### 1.2 Calendar

**Mechanism:** Also browser-cookie based, but hits the **real** (undocumented-auth) Calendar API `https://clients6.google.com/calendar/v3/calendars/primary/events` using **SAPISIDHASH** auth derived from the `SAPISID`/`__Secure-3PAPISID` cookie (`origin = https://calendar.google.com`), plus a required `GOOGLE_CALENDAR_API_KEY` env var (app-level API key, not per-user OAuth token). `daysBack: 365, daysForward: 30, maxResults: 500` (`ConnectorImportOperations.importCalendar`).
- Failure classes add `configuration` (bad/missing API key) on top of Gmail's set.
- Windows' existing Calendar path (`fetchCalendar` in `google.ts`) uses the standard `https://www.googleapis.com/calendar/v3` REST API with the OAuth access token — again the cleaner path, already built (feature-flagged off), next 14 days only currently.
- Note: backend also has `routers/google_calendar.py` (`GET` endpoints for a calendar **event picker** UI, backend-mediated OAuth via `utils/retrieval/tools/google_utils.refresh_google_token`) — a *third*, separate calendar integration used for chat-tool event creation, not the import connector. Don't conflate it with either Mac's or Windows' import path.

### 1.3 Memory/task write path (both Gmail and Calendar imports)

Two-tier save, same for both sources:
1. **Raw evidence save** — `saveAsMemories()`: one `ImportEvidenceBatchItem` per email/event (externalId `gmail:<id>` / `google_calendar:<id>`, occurredAt, title, snippet, content, metadata incl. `import_kind`).
2. **LLM synthesis save** — `synthesizeFromEmails`/`synthesizeFromEvents`: one Claude call (`AgentClient.run`, model `ModelQoS.Claude.synthesis`, i.e. `claude-haiku-4-5-20251001` per Windows' existing `memoryExtract.ts` comment) extracting ~10-15 profile memories + 2-5 tasks (via `TasksStore.shared.createTask`) as strict JSON, retried up to 2 attempts on transient failure (800ms backoff). System prompt: "You are a profile extraction assistant. Output ONLY valid JSON..."

Both funnel through `OnboardingImportEvidenceService.save(artifacts, sourceType, ...)`:
- Endpoint: **`POST v3/memory-imports/batch`** (`APIClient.createMemoryImportBatch`), body = `ImportEvidenceBatch{sourceType, importRunId, sourceAccountHash?, items}`, max **100 items/batch** (`memoryImportBatchMaxSize`), auto-chunked, retried on 429/5xx/network error (2s/5s/10s backoff).
- `importRunId` format: `"desktop-<normalized-source>-<uuid>"`.
- Each item stamped with `clientDeviceId` (`ClientDeviceService.shared.clientDeviceId`) for provenance.
- **Legacy fallback**: if the batch endpoint 404s (prod today lacks the canonical import router) or returns `403 memory_import_requires_canonical`, falls back to **`POST v3/memories/batch`** (`createMemoriesBatch`, `MemoryBatchItem[]`, max 100/`memoriesBatchMaxSize`) — the older, simpler memory-creation endpoint. **Windows must implement both paths and the same fallback trigger** since prod may still 404 the import-evidence route.

### 1.4 X / Twitter

**Backend-mediated OAuth2 + PKCE** (genuinely, unlike Gmail/Calendar):
1. `GET /v1/x/oauth-url?success_redirect_url=<app-deep-link>` → `{success, auth_url, error}`. Desktop opens `auth_url` in the system browser (`NSWorkspace.shared.open`). Deep link = `"<app-url-scheme>://x/callback"` (scheme read from `CFBundleURLTypes`, default `omi-computer`; dev vs prod builds differ).
2. X redirects to backend `GET /v2/integrations/x/callback?code&state` (in `x_connector.py` region not fully re-read here, but referenced) → backend exchanges code, stores tokens, **kicks off first sync in background**, HTML-redirects to the app's deep link.
3. Desktop polls `GET /v1/x/connection-status` (`XConnectionStatusResponse`: `success, connected, handle, post_count, memory_count, syncing, last_synced_at, last_sync_source`).
   - Phase 1 (`ConnectorImportOperations.connectX`): poll every 2s, up to 60 tries (~2 min), until `connected == true`.
   - Phase 2: poll every 2s, up to 90 tries (~3 min), surfacing live `post_count`/`memory_count`, until backend reports `syncing == false`.
4. Other routes: `POST /v1/x/sync` (manual re-sync), `POST /v1/x/disconnect`, `GET /v1/x/posts?kind=tweet|bookmark|like&limit=`.
- Backend owns all memory extraction from X posts server-side (not visible to desktop) — desktop only reads counts back.

### 1.5 ConnectorImportRunner (run-state manager — port this shape verbatim)

`@MainActor final class ConnectorImportRunner: ObservableObject`, singleton (`.shared`). Purpose: survive the import sheet closing/reopening, and prevent double-starts.

```
enum Phase { running, succeeded, failed }
struct RunState { phase, progressTitle, progressDetail, statusMessage?, errorMessage? }
struct ProgressSink { weak runner, connectorID, runToken(UUID) }  // update(title:, detail:) is a no-op if runToken is stale
@Published runs: [String: RunState]          // connectorID -> state
private tasks: [String: Task]                 // connectorID -> in-flight task
private runTokens: [String: UUID]             // connectorID -> current token (invalidates stale progress updates)

start(connectorID, progressTitle, progressDetail, operation: (ProgressSink) async -> RunOutcome) -> Task?
  // no-op (returns nil) if tasks[connectorID] already exists — de-dupes concurrent starts
isRunning(connectorID) -> Bool
acknowledgeSuccess(connectorID)  // clears a SUCCEEDED run once shown+dismissed; FAILED runs persist until next start
```

Design intent (memory-only, dies with process — no persistence): a run started from any of the 3 entry points must be globally keyed by connector ID so starting "Gmail import" from the Memories page and later opening onboarding's Data-Sources step (or the Apps hub) shows the **same in-flight/failed/succeeded state**, not a second concurrent run. Port this almost 1:1 as the shared run-state store (e.g. a Zustand/Redux slice or a singleton EventEmitter keyed by connector id) that all three Windows entry points read from.

### 1.6 ConnectorImportOperations (per-connector operation functions)

Pure `Outcome = success(SyncResult{sourceCount?, memoryCount?, newItems?}, message) | failure(message)` functions, one per connector, each taking a `ProgressSink` for live progress text. This is the natural shape for the unified capability's per-connector adapters: `importGmail(progress) -> Outcome`, `importCalendar(progress) -> Outcome`, `connectX(progress) -> Outcome`, plus Mac-only local ones (Apple Notes, local file rescan, memory-log paste) that Windows won't port as-is (Windows has its own Sticky Notes analog already).

---

## 2. EXPORTS / MCP (Mac)

### 2.1 `MemoryExportDestination` enum — 10 cases, 3 tiers

```
notion, obsidian, chatgpt, claude, gemini, agents, claudeCode, codex, openclaw, hermes
```

Three delivery tiers per destination (drives the UI at all 3 entry points):
- **`supportsMemoryPack`** (`notion, obsidian, chatgpt, claude, gemini`) — one-time copy/paste Markdown snapshot. "MANUAL" tag.
- **`supportsMCP`** (`chatgpt, claude, claudeCode, codex, openclaw, hermes`) — live MCP connection, "AUTOMATIC" tag. Sub-split by `mcpExecuteKind`:
  - `.localAutonomous` (`claudeCode, codex, openclaw, hermes`) — deterministic local file/CLI write, no browser needed.
  - `.assisted` (`chatgpt, claude, notion, obsidian, gemini` — note notion/obsidian/gemini fall here too even though they don't `supportsMCP`, `mcpExecuteKind` is defined for all cases) — Omi opens the destination + copies a value, user finishes manually.
  - `.browserAutonomous` — currently **unmapped to any case** (comment: ChatGPT/Claude moved off this because cross-browser AX automation was too brittle).
- **`supportsAgentSetup`** (`agents` only) — the "Let your agent do it" one-prompt flow bundling MCP + local Omi CLI access + a guide.

`hasLocallyVerifiableLiveSetup` (`agents, claudeCode, codex, openclaw, hermes`) = true → status can be verified by reading local files, no live probe needed.

### 2.2 Hosted MCP server + key minting

- Server URL: `MemoryExportDestination.mcpServerURL = "{mcpBaseURL}v1/mcp/sse"` where `mcpBaseURL = DesktopBackendEnvironment.pythonBaseURL()` (prod `api.omi.me`, dev `api.omiapi.com`).
- Auth: per-user bearer key. **Mint endpoint: `POST /v1/mcp/keys`** body `{name: string}` → `McpApiKeyCreated{...key}` (backend `routers/mcp.py:106`). Windows equivalent call: `APIClient.shared.createMCPKey(name: "Omi Desktop")` → `POST v1/mcp/keys`.
- `MemoryExportService.ensureMCPKey()`: returns cached key (UserDefaults, scoped to `authUserID` so switching accounts invalidates it) or mints a fresh one; de-dupes concurrent mint calls via an in-flight task keyed by owner user id. `createNewMCPKey()` forces a fresh mint (used by "New key" button). Also `GET /v1/mcp/keys` (list) and `DELETE /v1/mcp/keys/{key_id}` exist server-side but aren't exercised by this sheet.
- Live test: `testAgentConnections` POSTs a raw JSON-RPC `tools/call` (`get_memories`, `limit: 5`) to `mcpServerURL` with `Authorization: Bearer <key>` to prove the hosted key works.

### 2.3 Local coding-agent CLI config writers (`MemoryBankConnector.swift`) — exact paths + block shapes

All four are `.localAutonomous`, deterministic, idempotent (skip write if config already matches), and require the tool to be locally detected first (else throws `notInstalled`). **Port these paths verbatim, substituting `~` → `os.homedir()` on Windows** (same relative subpaths — these are cross-platform CLI config files, not macOS-specific).

**Claude Code** — `~/.claude.json`, key `mcpServers.omi-memory`:
```json
{
  "mcpServers": {
    "omi-memory": {
      "type": "http",
      "url": "<mcpServerURL>",
      "headers": { "Authorization": "Bearer <key>" }
    }
  }
}
```
Detection-also-checked: `~/.claude/settings.json` existence, or `claude` on PATH. Backs up prior `.claude.json` to `~/.claude/backups/.claude.json.backup.<epoch-ms>-<uuid>` before writing (keeps 5 most recent). Verifies write via `MemoryExportConnectionDetector` re-read after writing.

**Codex** — no direct file write; runs the CLI itself:
```
codex mcp add omi-memory -- npx -y mcp-remote <mcpServerURL> --header "Authorization: Bearer <key>"
```
(with `CODEX_HOME=~/.codex` env var set, dir created if missing). Detection: `codex` executable on PATH or common dirs.

**OpenClaw** — `~/.openclaw/openclaw.json`, requires the OpenClaw CLI (`openclaw`) on PATH and an existing workspace (queried via `openclaw config get agents.defaults.workspace`, fallback `~/.openclaw/workspace`). Writes via the CLI: `openclaw mcp set omi-memory '<json>'` then `openclaw mcp reload`. Server JSON block:
```json
{
  "enabled": true,
  "url": "<mcpServerURL>",
  "transport": "streamable-http",
  "headers": { "Authorization": "Bearer <key>" }
}
```
Also appends a marked note block to `<workspace>/SOUL.md` (idempotent via `<!-- omi-memory-bank -->` marker):
```
<!-- omi-memory-bank -->
## OMI memory (search FIRST)
Omi is your memory bank. Before any task, call the OpenClaw MCP tool `omi-memory__search_memories` for context. Use `omi-memory__get_conversations`, `omi-memory__get_daily_summaries`, or `omi-memory__get_screen_activity` when the user asks about activity/history. Save durable new facts with `omi-memory__create_memory`. Do not substitute OpenClaw's local `memory_search` or `memory_get` tools for Omi memory.
<!-- /omi-memory-bank -->
```

**Hermes** — `~/.hermes/config.yaml`, top-level YAML key `mcp_servers` (hand-rolled YAML text insertion, not a YAML library — matches indentation manually):
```yaml
mcp_servers:
  omi-memory:
    command: npx
    args: ["-y", "mcp-remote", "<mcpServerURL>", "--header", "Authorization: Bearer <key>"]
```
Requires `~/.hermes/config.yaml` to already exist plus install evidence (`~/.hermes/.install_method` or `~/.hermes/hermes-agent/hermes`, or a valid `~/.hermes/hermes-agent/package.json` with `name: "hermes-agent"`). Also appends the same-shaped "search Omi first" note to `~/.hermes/SOUL.md`.

**Connection-status detection** (`MemoryExportConnectionDetector.swift`) — scans these exact files for the `mcpServerURL` string + bearer key match, independent of the writer above (used to show "Connected" without re-running the writer):
```
~/.codex/config.toml                                      -> .codex
~/Library/Application Support/Claude/claude_desktop_config.json -> .claude   (macOS-only path — Windows equivalent is %APPDATA%/Claude/claude_desktop_config.json)
~/.claude.json                                             -> .claudeCode
~/.claude/settings.json                                    -> .claudeCode
~/.openclaw/openclaw.json                                  -> .openclaw
~/.hermes/config.yaml                                      -> .hermes
```

### 2.4 Notion push

Notion is **NOT a live connector** — it's `supportsMemoryPack` only (no MCP, no backend push endpoint found in this read). Flow: `MemoryExportService.prepareManualExport(for: .notion)` generates a Markdown memory pack, copies it to clipboard, saves a local backup file, reveals it in Finder, and opens Notion in the browser — the user pastes it in manually. No backend Notion API integration exists for desktop exports.

### 2.5 ChatGPT / Claude cloud connectors (OAuth PKCE)

Both are `supportsMCP` + `supportsMemoryPack`. The "manual setup" disclosure shows MCP server URL + OAuth Client ID for their native "custom connector" UI:
- `mcpAuthorizeURL = "{mcpBaseURL}authorize"`, `mcpTokenURL = "{mcpBaseURL}token"`.
- ChatGPT client id: `chatgptOAuthClientID` = `"omi-chatgpt-prod"` (prod, `api.omi.me`) or `"omi-chatgpt-dev"`. **Public PKCE client — no secret**, `cloudTokenAuthMethod = "none"`.
- Claude client id: `"omi-claude-prod"` (both channels), secret also nil — public PKCE client. Claude's UI additionally needs a "Name" field (`"Omi Memory"`) since its custom-connector form asks for one.
- These are backend-registered OAuth clients (`MCP_OAUTH_CLIENTS_JSON` env, per root `AGENTS.md` service map) — desktop just displays the values; ChatGPT/Claude's own product UI drives the actual OAuth handshake.
- Both also fall back to `supportsMemoryPack` (copy prompt + Markdown export + open the site) since MCP setup there is a manual paste of URL/client-id into their settings, not a fully automatable flow — hence `mcpExecuteKind == .assisted` for both.

### 2.6 The 3-tier decision surfaced in the sheet UI

For any `supportsMCP` destination, the sheet shows, in order:
1. **"Let Omi do it" / Execute** (primary CTA, tag "FASTEST") → `MemoryExportExecutor.run(destination)` — routes to `.localAutonomous` (deterministic write, e.g. `MemoryBankConnector.connect`), `.browserAutonomous` (unused currently), or `.assisted` (open + copy + on-screen guidance card).
2. **Manual disclosure** (collapsed by default) → "Live connection" (AUTOMATIC tag): raw MCP server URL + key fields for manual paste.
3. **Memory pack** (MANUAL tag, only if `supportsMemoryPack`): one-time Markdown snapshot copy/export.

---

## 3. BACKEND — routes and platform recognition

| Route | Method | Purpose |
|---|---|---|
| `v3/memory-imports/batch` | POST | Canonical import-evidence batch write (max 100/req); may 404/403 on deployments without the canonical import router → legacy fallback. `includeBYOK: false`. |
| `v3/memories/batch` | POST | Legacy batch memory create (max 100/req) — fallback target. |
| `v3/memories` | POST | Single memory create (used by Sticky Notes on Windows today). |
| `v1/mcp/keys` | GET/POST/DELETE | List / mint / revoke per-user hosted MCP bearer keys (`routers/mcp.py`). POST body `{name}` → `{..., key}`. |
| `v1/mcp/oauth/grants`, `v1/mcp/oauth/grants/{id}` | GET/DELETE | List/revoke MCP OAuth grants (ChatGPT/Claude connectors). |
| `v1/x/oauth-url` | GET | `?success_redirect_url=` → `{success, auth_url, error}`. Backend-mediated PKCE start. |
| `v2/integrations/x/callback` | GET | X's OAuth redirect target; exchanges code, stores tokens, kicks off first sync, HTML-redirects to app deep link. |
| `v1/x/connection-status` | GET | Poll target: `{success, connected, handle, post_count, memory_count, syncing, last_synced_at, last_sync_source}`. |
| `v1/x/sync` | POST | Manual re-sync. |
| `v1/x/disconnect` | POST | Disconnect. |
| `v1/x/posts` | GET | `?kind=tweet\|bookmark\|like&limit=` — read back synced posts. |
| `v1/google-calendar/*` | GET | `routers/google_calendar.py` — a **separate** backend-OAuth calendar integration for the chat-tool event picker (`utils/retrieval/tools/calendar_tools.py`), unrelated to the import connector. Don't reuse for imports. |

**Platform recognition**: `'windows'` **is** a recognized platform value server-side (contrary to some prior parity findings elsewhere in this codebase) —
- `database/users.py:37`: `'windows': 'desktop'` (platform-family mapping)
- `utils/subscription.py:119`: `DESKTOP_PLATFORMS = {'macos', 'windows'}`
- `utils/subscription.py:457`: `'windows': NEW_PLANS_MIN_WINDOWS_VERSION`
- `utils/llm/chat.py:434`: a `'windows':` branch exists (platform-specific chat tool copy)
No connector-specific backend code branches on platform at all — imports/exports/MCP routes are platform-agnostic (uid-scoped only), so no server-side gating risk for Windows here.

---

## 4. Windows current state (baseline to build on, not from scratch)

Already shipped (unflagged): Notion export (`memoryExport/notion.ts`), Obsidian export (`memoryExport/obsidian.ts`), plain-Markdown file export (`memoryExport/plainFile.ts`) — all `IPC: memoryExport:{obsidian,file,notion}`, renderer owns fetching memories + API token, main does fs/network. Also Sticky Notes import (LLM-synthesized, writes via plain `POST /v3/memories`) and memory-log paste import (`memoryExtract.ts`, ports Mac's `OnboardingMemoryLogImportService` prompt verbatim over `desktopApi.post('/v2/chat/completions', ...)`).

Already built but **feature-flagged off** (`VITE_ENABLE_GOOGLE_INTEGRATION`): real Gmail + Calendar OAuth 2.0 PKCE (loopback flow, `oauth.ts`), REST reads (`google.ts`), incremental sync-state (`syncState.ts`), IPC (`ipc/integrations.ts`), UI (`IntegrationsTab.tsx`'s "Google (Gmail + Calendar)" row). This is functionally Track 3/6's Gmail+Calendar import connector already — it needs: (a) the `ImportEvidenceBatchItem`/`v3/memory-imports/batch` write path (currently writes plain memories/action-items directly, no import-evidence provenance or legacy-fallback logic), (b) the run-state manager shape (§1.5), (c) unflagging + UI promotion into the unified sheet.

**Not yet present on Windows at all**: X/Twitter import connector, MCP hosted-key minting/storage, MCP server URL export, any local coding-agent CLI writers (Claude Code/Codex/OpenClaw/Hermes), ChatGPT/Claude cloud OAuth connector display, the "Agents" one-prompt setup, `ConnectorImportRunner`-equivalent shared run-state.
