# Mac-Parity Parallel Execution Plan — 4 Worktree Streams

> Splits the ~200-item parity audit (see [00-INDEX.md](00-INDEX.md)) into **4 workstreams for 4
> Claude Code sessions running simultaneously in 4 linked git worktrees**. Optimized for
> (a) minimal file collisions between streams, (b) dependency order (enabler infra first),
> (c) deduplicated items (several gaps were documented 2–3× across audit files).
> Produced 2026-07-13 from a per-area dependency/collision analysis of all 13 audit files.

## Launch runbook (2026-07-13)

1. Merge `fix/windows-wiring-criticals`.
2. Finish + merge `feat/windows-settings-parity` (one trivial import conflict in `main/index.ts`).
3. Pin ALL streams' Mac references to one captured upstream commit at spawn time (Stream 1's
   v0.12.72 pin extends to all — don't let streams drift to different Mac snapshots).
4. Provision per-stream test accounts OR serialized live-test windows + mandatory fixture
   teardown — 4 streams share ONE backend uid today; interleaved chat threads/extractions are
   the top cross-stream risk.
5. Stagger CI pushes.
6. Each stream lands its additive `db.ts` schema PR first, immediately.
7. Spawn the 4 streams from post-merge `main`.

## Before the streams start (pre-work, one small PR)

1. ~~Fix the purple `--accent` violation (URGENT, INV-UI-1)~~ — **already fixed on `main`**:
   `src/renderer/src/styles/globals.css:62` is `--accent: #ffffff` with an explicit INV-UI-1
   comment. No pre-work PR needed for this item.
2. **Branch protocol.** Each stream: `git fetch origin && git worktree add .worktrees/<name> -b
   <branch> origin/main`, then `cd desktop/windows && pnpm bootstrap`. Small PRs to fork `main`,
   merged fast (regular merge, never squash), rebase onto `origin/main` after every merge —
   the shorter the divergence window, the fewer conflicts on the shared hotspots below.

## Default engineering posture (applies to every stream)

**Port Mac's logic and wiring faithfully — it's the proven implementation.** Read the Mac source
for the feature first and reuse its state machines, thresholds, endpoint usage, and edge-case
handling rather than re-deriving them. Deviate only when:
1. the wiring audit (WIRING-AUDIT.md) proved Mac itself is wrong (e.g. goal-completion PATCH
   fields, memory-edit body-vs-query-param — use the backend contract as the reference there), or
2. Windows is documented as ahead (see "Windows-ahead" list in 00-INDEX.md), or
3. the platform genuinely forces a different mechanism (CoreAudio→WASAPI, Keychain→DPAPI, etc.) —
   in which case match Mac's *behavioral contract*, not its API calls.
Don't overdo it either — a faithful port of the behavior, not a line-by-line transliteration of
Swift into TypeScript.

## The four streams

### Stream 1 — Agent runtime & chat platform  (branch: `feat/win-agent-kernel`)
*Core of audit area 04, plus the chat-rendering items that areas 06 and 13 flagged against the
same files. Everything other streams block on — staff this one first.*

- Kernel: sessions / runs / attempts / turns / artifacts in SQLite (port of Mac's
  `sqlite-store.ts` schema: sessions, runs, adapter_bindings, run_attempts, events, artifacts,
  delegations, grants). Today Windows has **no persistence** — every task is a fresh
  `openBinding`; `resumeBinding` is modeled but never called.
- Agent control plane: list / inspect / cancel / spawn / send tools (Mac injects 18 control
  tools regardless of provider) + intent router + real tool-policy engine (replacing
  `toolPolicyStub.ts` — keep its host-owned-identity invariant, INV-AGENT (b)).
- Background delegation UX: bar **agent pills** (Mac: dismissible pill + status poll + voice
  follow-up via `continueAgent`) — Windows currently blocks a chat bubble for the task duration.
- Structured content blocks in chat: tool-call / thinking / agent-activity / discovery cards,
  markdown **tables** (GFM), typing indicator, citation cards — one content-block model in
  `ChatMessages.tsx` (this single fix was independently demanded by areas 04, 06 AND 13).
  **Data plumbing is done** (fixed on `fix/windows-wiring-criticals`, 2026-07-13): the `done:`
  payload's `serverId`/`citations`/`chartData`/`askForNps` are now parsed and stored (C4).
  Remaining scope here is **rendering only** — wiring those fields into `ChatMessages.tsx`'s
  card UI. (The stream's "no abort path" framing is also stale — C5 fixed it: AbortController +
  generation counter + 180s watchdog + agent-task guard, in `useChat.ts`.)
- Chat sessions sidebar (multi-thread history, date-grouped/starred/searchable) + session data
  layer.
- Chat attachments, resources/artifacts, stall-detection banner, structured error taxonomy.
- `localAgent.ts` enrichment loop (`ENRICH_ENABLED=false` today): re-enable as part of the real
  tool-calling loop, with the latency budget that got it disabled (~2.5s) engineered out —
  area 11 calls this a "flag flip," area 04's framing (needs the full loop) is the correct scope.
- `screenContext.ts` upgrade: screen context **as image** (Mac sends `imageBase64` in the kernel
  query + structured envelope; Windows sends OCR text prepended to the user message).
- Wiring-audit fixes in this stream's files: multi-provider external agents already work via
  Settings commands — extend, don't rebuild.

Mac-beta spec notes that shape this stream (from the v0.12.72 tag read):
- Mac's **default provider is `pi-mono`** — an in-process SDK agent proxied through Omi's backend
  (no CLI, works for any signed-in user). Windows' default is Claude Code over ACP (rides the
  user's own `~/.claude` login). Whether Windows should add a pi-mono-equivalent zero-setup
  default is a product decision (gate below).
- Mac routes bar text through an LLM intent classifier (Haiku, ~300-500ms) to pick chat vs
  agent; Windows uses a conservative regex (`detectAgentTask`). Consider upgrading when pills land.
- Mac has a **second, disconnected agent system** (`TaskAgentManager`: shells
  `claude --dangerously-skip-permissions` in tmux for proactive task extraction) — scope it out
  of this stream explicitly; if ever wanted it belongs to Stream 3's task-extraction work.
- Post-beta upstream commits are converging on "kernel as the single run authority" +
  voice-transcript-derived consent for permission requests — don't over-fit the port to the
  v0.12.72 multi-owner model.

**Owns (exclusive write access):** `hooks/useChat.ts`, `components/chat/ChatMessages.tsx`,
`lib/chatConversation.ts`, `lib/localAgent.ts`, `lib/screenContext.ts`, `lib/agentTask.ts`,
`main/codingAgent/**`, new `main/agentKernel/**`.
**Publishes contracts for others:** tool surface (get_tasks / get_memories / search_screen /
spawn_agent / …), kernel session API, content-block message model. Publish the TypeScript
interfaces early (first PR) so Streams 2–3 can code against them.

### Stream 2 — Voice & bar depth  (branch: `feat/win-voice-depth`)
*Areas 06 + 07 minus the chat-rendering items (Stream 1 owns those files).*

Phase A (independent of Stream 1 — start immediately):
- **TTS read-aloud** of AI replies in the bar + barge-in interrupt (Mac: cloud TTS proxy via
  desktop backend, local synth fallback).
- PTT **vocabulary boosting** (screen OCR + recent activity → `keywords` param on
  `/v2/voice-message/transcribe-stream` — Mac sends it, Windows doesn't).
- PTT spoken-**language auto-detection**; **system-audio mute/duck** during capture.
- Warm-hub **system-wide PTT**: global hotkey wiring into the realtime session (Windows'
  realtime voice is currently a page-bound button session), per-provider barge-in
  (OpenAI `response.cancel` vs Gemini session-replace + token re-mint), idle/wake reconnect.
- Auto "Auto" model selection; rich per-session system instructions; `<about_user>` context
  card (area 03/06 flagged it, but its only real Mac consumer is the realtime hub → owned here).
- Usage limiter for the bar (⚠ pending the product decision below).
Phase B (consumes Stream 1's tool surface — do last):
- **In-session tool-calling** (voice-as-router, ~20 tools) — literally requires Stream 1's tool
  surface; do not build a parallel one.
- Voice turns recorded into shared chat/kernel history (incl. barge-in partials); in-turn
  screen/vision context.

**Owns:** `lib/voice/**`, `lib/ptt/**`, `main/bar/**`, `main/overlay/**`, `components/bar/**`,
`components/voice/**`, orb components, `components/overlay/Waveform.tsx`.
**Must NOT edit:** `useChat.ts`, `ChatMessages.tsx`, `screenContext.ts` — request changes from
Stream 1 (message its session or leave an interface note in the PR).
⚠ Do not regress Windows-ahead items: adaptive noise-floor waveform, orb visual system.

### Stream 3 — Proactive intelligence & memory  (branch: `feat/win-proactive`)
*Areas 03 + 01 + 02 + the connector capability that areas 03/10/12 each asked for separately.*

Sequenced — the first two items are enablers everything else here reads from:
1. **AI User Profile** (quick win: `get/update_ai_profile` endpoints already in the generated
   client with zero callers) — daily synthesis doc that grounds Focus/Insight prompts, task
   prioritization and goal generation.
2. **Assistant coordinator framework** (Mac's `AssistantCoordinator`: context-switch detection,
   backpressure, orchestration policy, notification throttling) — the substrate for items 3–6.
3. **Focus assistant** (per-screenshot attention judging + nudges + session history/score +
   daily score) and the **glow overlay** (areas 01 and 13 documented this same feature twice —
   one work item, owned here).
4. **Insight assistant depth** (two-phase SQL-investigation + vision confirm, backend-synced as
   searchable memory, history UI). Audit calls insight backend-sync the cheapest high-value win
   in area 01.
5. Continuous **AI memory extraction** (screen → LLM → confidence-gated memory, dedup) and
   screen-based **AI task extraction** (staged-tasks pipeline: backend `/v1/staged-tasks` with
   relevance scores + promote flow already exists server-side).
6. **Auto daily goal generation** + stale-goal cleanup + goal **advice** (quick win: endpoint
   exists, richer than Mac's local version). Note: Mac never calls `/v1/goals/suggest` — it
   generates goals client-side with full context (500 memories / 100 conversations / 100 tasks).
   Decide per-item whether to match Mac's client-side generation or use the backend endpoint.
7. **Semantic embeddings** service (tasks/memories ranking; Windows is lexical-only).
8. **Unified connectors capability** — ONE implementation of "read external source → import +
   LLM-synthesize" (Gmail, Calendar) and MCP memory-export destinations (Notion push;
   Claude Code/Codex/OpenClaw/Hermes = local config wiring to Omi's hosted MCP server;
   ChatGPT/Claude = OAuth PKCE). Areas 03, 10 and 12 each specified this independently —
   build once here, expose three entry points: Memories page, onboarding Data-Sources step,
   Apps marketplace Imports/Exports hub. (The Apps-page UI shell itself is Stream 4's; it mounts
   this stream's capability.)
- Per-task "Investigate" chat and autonomous task-agents need Stream 1's kernel — sequence last
  or hand off to Stream 1 when its kernel lands.

**Owns:** `lib/insight*`, new `main/assistants/**`, `main/memoryExport/**`, `main/memoryImport/**`,
`main/memoryCleanup/**`, `hooks/useMemories.ts`, `lib/memoriesBulk.ts`, `lib/memoryExtract.ts`,
`pages/Memories.tsx`, `lib/goals.ts`, `pages/{Tasks,Goals}.tsx`, home widgets
(`QuickTaskWidget`, `QuickGoalsWidget`), `components/settings/tabs/IntegrationsTab.tsx`,
`components/insight/**`.
⚠ Parked pending decisions: **Persona** (backend routes don't exist even in the generated
client — it's a backend project, not a client port).

### Stream 4 — Rewind, conversations & shell  (branch: `feat/win-rewind-shell`)
*Area 05 + the 12/13 items that belong to Rewind/Conversations/shell + area 11's file-index
items + area 10's local onboarding steps. The most self-contained stream.*

- **Rewind search UI un-gating** (quick win: fully built, dead `showSearch` flag) → then
  **OCR-embedding semantic search** (vs `LIKE`), FTS5, OCR bounding boxes / on-image highlight.
- **Storage architecture**: video-chunk (H.265) vs per-frame JPEG decision (⚠ decision gate
  below, DECIDED — keep JPEGs for now, see Gate 2) + the wiring-audit fixes that are this
  stream's files anyway: 30s keyframe anchor, battery-aware cadence, suspend/resume handling,
  orphaned-JPEG cleanup, OCR re-backfill. ~~OCR-helper `dispose()` on quit~~ (fixed on
  `fix/windows-wiring-criticals`, 2026-07-13).
- Date navigation (browse any day), full-screen timeline player (transport controls), DB
  corruption recovery; action-item + observation extraction from screen.
- **LiveNotes** (auto meeting-minutes during recording — flagged by 05 and 12, one owner: here).
- **Speaker naming** (live + post-hoc person picker) + per-speaker color coding (12 + 13, same
  files: `ConversationDetail.tsx`, `LiveConversation.tsx`, `TranscriptPopup.tsx`).
- Shell/settings: ~~Settings inventory 6→11 sections~~ narrowed to **Notifications tab**
  (blocked on Stream 3's proactive assistants) **+ global settings search** — Plan & Usage /
  Transcription / Shortcuts / About are being built on `feat/windows-settings-parity` instead —
  + Permissions repair page, Help/support page (⚠ Crisp decision below), redesigned Home (stat
  ribbon, connect-data tray — mounts Stream 3's widgets/capabilities but owns the page), sidebar
  changes, crash/clean-exit detection (wiring-audit Major), launch-at-login default migration.
- File index (11): scan-dir skip-list fix (21 dirs vs 4), incremental 3h re-scan,
  **BrainGraph interactivity flip** (quick win: `interactive={false}` everywhere + standalone
  viewer route + rebuild button), onboarding file-scan **entity extraction** (LLM exploration →
  KG nodes; co-design with Stream 3's synthesis patterns but implemented against this stream's
  fileIndex/KG files).
- Onboarding local steps (10): multi-language select, memory-log import UI wiring, file-scan
  depth. (Web research + data-source synthesis are Stream 3's connector capability.)

**Owns:** `main/rewind/**`, `main/ocr/**`, `pages/Rewind.tsx`, `hooks/useRewind.ts`,
`components/rewind/**`, `pages/{Conversations,ConversationDetail,LiveConversation}.tsx`,
`components/TranscriptPopup.tsx`, `pages/{Home,Apps,Settings}.tsx`, `components/layout/**`,
`components/settings/**` (except IntegrationsTab → Stream 3), `App.tsx`, `main/fileIndex/**`,
`main/ipc/{kg,kgWorker,kgWriteQueue,localGraph}.ts`, `components/graph/**`,
`components/onboarding/**`, `main/{sentry,updater,lifecycle}.ts`.

### Explicitly parked (not in any stream)
- **BLE / wearables (08) + WAL offline sync (09).** 09 is hard-blocked on 08 ("no frame source
  to buffer"); together they're a self-contained XL subsystem with zero file overlap with
  anything else — the ideal 5th stream *whenever wanted*, but it needs physical devices to
  verify, so don't burn one of the 4 seats on it.
- **Persona / AI-clone** — backend routes missing entirely (see Stream 3 note).

## Shared-file collision rules (the merge-conflict hotspots)

| File | Owner | Others must |
|---|---|---|
| `hooks/useChat.ts`, `components/chat/ChatMessages.tsx`, `lib/screenContext.ts`, `lib/localAgent.ts` | Stream 1 | request changes, never edit |
| `lib/goals.ts`, `hooks/useMemories.ts`, `IntegrationsTab.tsx` | Stream 3 | request changes |
| `main/bar/window.ts`, `lib/voice/tts.ts` | Stream 2 | request changes |
| `pages/Home.tsx`, `Sidebar.tsx`, `App.tsx`, `pages/Apps.tsx`, settings tabs | Stream 4 | Stream 3 mounts widgets via props/exports only |
| `main/ipc/db.ts` (SQLite schema) | shared | **additive-only**: each stream appends its own `ensureColumn`/`CREATE TABLE IF NOT EXISTS` block at the end of its own clearly-labeled section; never reorder; land schema PRs immediately |
| `src/shared/types.ts`, `src/preload/index.ts` | shared | additive-only, same rule |
| `pnpm-lock.yaml` | shared | on conflict: take main's + re-run `pnpm install` |
| `capture/liveRescue.ts`, `capture/liveMicSession.ts`, `main/ipc/omiListen.ts` | **settled** (wiring branch) | Streams request changes, never edit |
| `lib/authSession.ts`, `lib/authTeardown.ts`, `lib/apiClient.ts` | **settled** (auth) | standalone-PR changes only |
| `lib/sync/outboxSweep.ts`, `main/ipc/dbWipe.ts`, `lib/settingsNav.ts`, new settings tabs (PlanUsage/Transcription/Shortcuts/About) | Stream 4 | request changes |
| `lib/localAgentMemoryCache.ts` | Stream 1 | request changes |
| `main/billing/**`, `lib/billing.ts`, `lib/usageLimit.ts` | settings-parity work | Stream 2 CONSUMES for the bar usage-limiter (reuse, don't rebuild) |
| capture-core / auth / sync files (merged from `fix/windows-wiring-criticals`) | **settled** | request changes, do not edit |

## Decision gates for Chris (park, don't guess)

1. **Trial/paywall + usage limiter** — **RESOLVED.** Plan & Usage tab + usage-limit popup built
   on `feat/windows-settings-parity`; residual scope is product policy only.
2. **Rewind storage architecture** — **DECIDED**: keep JPEGs + retention tuning for now; H.265
   revisit after Stream 4's other work lands. BLOCKS-MID-STREAM only — everything else in
   Stream 4 proceeds regardless.
3. **Help/Crisp** — open, low priority, mid-stream (Stream 4). About tab links `help.omi.me`
   meanwhile.
4. **Persona** — needs backend routes built first; separate project. Unchanged, parked.
5. **BLE stream** — when (if) to start the 5th stream; needs test hardware on the Windows box.
   Unchanged, parked.
6. **Citation metadata** — **mostly resolved**: backend confirmed sending memories citations in
   the `done:` payload and Windows now stores them (C4). Residual = `chart_data` rendering only.
7. **Agent default provider** — **DECIDED**: `pi-mono` default, as implemented on Mac
   (in-process SDK, Omi-proxied, zero-setup; not everyone has Claude Code). Claude Code remains
   the power-user option. Stream 1 owns the pi SDK port + proxy auth.
8. **Default chat architecture** — **DECIDED**: the kernel is the target for DEFAULT chat too,
   but STAGED — Stream 1 ports the kernel + pi-mono for agent sessions first, implements the
   `/v2/desktop/messages` persistence contract, then flips default chat as a distinct milestone
   with explicit verification: (a) shared-thread continuity proven against mobile in both
   directions (locked invariant), (b) grounding at least as good as the backend path, (c)
   feature-flag fallback to backend chat for the first release. **Required safeguards on the
   flip (hard requirements, not intentions):**
   - **Flag default-OFF shipping**: default chat stays on the backend `/v2/messages` path until
     every criterion below is green; the kernel flip is a runtime feature flag that ships OFF in
     the first release containing the kernel. Flipping it is its own decision point with Chris.
   - **Kill switch**: the same flag is a live kill switch — flipping back requires no migration,
     no data repair, at any time. Kernel chat persistence must therefore be ADDITIVE alongside
     the existing local chat store: no rewrites/moves of existing chat history, no destructive
     schema changes (`db.ts` additive-only rule applies doubly here).
   - **No one-way doors**: kernel session/run state lives in its own tables; nothing in the flip
     may alter or migrate existing conversations/messages such that the backend path can't
     resume them unchanged.
   - **Continuity invariant guarded by test**: shared chat continuity gets a guard test BEFORE
     the flip — a turn sent via kernel chat must appear in the backend thread (via the
     `/v2/desktop/messages` persistence contract) and turns from mobile must appear on Windows,
     verified both directions against a real second client.
   - **Fallback telemetry**: any runtime fallback from kernel → backend chat calls the shared
     `recordFallback` helper (`component=chat, from=kernel, to=backend, outcome`) — silent ops
     is banned by repo policy.
   - **Failure containment**: a kernel crash/hang must degrade to the backend path within one
     turn (watchdog + auto-fallback), never a dead chat UI.
   - **Rollout order**: agent sessions on kernel first (lower blast radius, already the plan) →
     internal/dev flag-on for daily use → only then consider default-on, staged per
     release-channel (beta before stable).
9. **Mac's System B (`TaskAgentManager`)** — **DECIDED**: skip. Upstream is consolidating on the
   kernel as single run authority; any future proactive task agent is kernel-based.

## Parked tasks — ownership assignment

- **BYOK** (key store + `withByokHeaders` helper): Stream 1 builds and publishes it as a
  contract; Stream 2 attaches it to the listen socket.
- **Firebase-token → DPAPI migration**: standalone small PR, not inside any stream; fallback
  owner is Stream 4 if it doesn't get picked up independently.

## Cross-cutting corrections the audit produced (so streams don't chase ghosts)

- The "Windows feeds only ~20 truncated memories vs Mac's full context" goal-suggest claim is
  wrong as stated: `GET /v1/goals/suggest` takes **zero** caller payload — the ~20-memory
  truncation is the backend's own behavior. The real difference: Mac doesn't use that endpoint
  at all (client-side generation with full context).
- Memory review-queue endpoints are dead codegen on **both** platforms — not a Windows gap.
- Windows-ahead items (do NOT "fix" toward Mac): adaptive-noise-gate waveform, local KG schema
  (summary/aliases/sourceRefs superset), one-shot UI-automation planner, markdown link safety,
  tray per-state icons, `SENSITIVE_WINDOW_MARKERS` private-browsing exclusion, idle-based
  capture pause, conversation outbox CAS+dedupe.

## How this maps back to the audit files

| Stream | Audit areas |
|---|---|
| 1 | 04 (all) + 13 (chat cards/tables/typing/citations/sessions sidebar) + 06 (chat rendering) + 11 (localAgent flag) |
| 2 | 06 (voice/PTT depth) + 07 (all) + 03/06 (`<about_user>` card) |
| 3 | 03 (minus persona) + 01 (all) + 02 (all) + 10 (web research, data sources, enrichment, exports capability) + 12 (Imports/Exports hub capability) + 13 (glow overlay) |
| 4 | 05 (all) + 11 (rest) + 12 (LiveNotes, speaker naming, settings, permissions, help, home) + 13 (Rewind visuals, speaker colors, font scale, design tokens) + 10 (local steps) |
| parked | 08, 09, persona |
