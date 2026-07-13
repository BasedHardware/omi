# Mac→Windows Parity Audit — Chat + Agent Runtime (ACP)

> Scope: the macOS desktop app's chat surface plus its full agent-runtime stack — the Node.js coding-agent runtime (ACP JSON-RPC over stdio), the "kernel" (sessions/runs/attempts/turns/artifacts), the desktop agent control plane (tools the agent can call to drive the app and to spawn/inspect/cancel other agents), floating-bar background-agent delegation, and chat depth (attachments, resources/artifacts, continuity, screen-context injection, stall detection, Claude auth). Windows baseline checked: `desktop/windows/src/renderer/src/hooks/useChat.ts`, `components/chat/ChatMessages.tsx`, `lib/chatConversation.ts`, `lib/localAgent.ts`, `lib/actionPlanner.ts`, `lib/agentLLM.ts`, `lib/screenContext.ts`, and a repo-wide grep for `codingAgent|claude-agent-acp|agent-client-protocol|spawn_agent|AgentPill|AgentRuntimeProcess` (zero hits outside macOS). PR-stack overlap (issue #9302, `feat/win-agents-1..4`) noted inline per feature — only PR 1/4 (#9304, "coding-agent ACP adapter core") is currently open; parts 2–4 (routing/fallback/IPC, settings UI, docs+fixes) do not exist yet as PRs.

## Summary table

| Feature | Mac location(s) | Windows status | Covered by feat/win-agents PRs? | Value (H/M/L) |
|---|---|---|---|---|
| ACP JSON-RPC coding-agent client (spawn Claude Code/Codex/Hermes/OpenClaw over stdio) | `agent/src/adapters/acp.ts`, `acp-bridge/` | Absent | Yes (#9304 ports this exact layer) | H |
| Adapter registry / selection (piMono vs acp vs hermes vs openclaw) | `agent/src/runtime/adapter-registry.ts`, `adapter-selection.ts`, `Providers/AgentRuntimeRouting.swift` | Absent | Yes (#9304 adds `adapterRegistry.ts`) | H |
| Kernel: sessions/runs/attempts/turns/artifacts persisted in SQLite | `agent/src/runtime/kernel*.ts`, `sqlite-store.ts` | Absent | No | H |
| Agent control-plane tools (`list_agent_sessions`, `get_agent_run`, `cancel_agent_run`, `spawn_agent`, `send_agent_message`, `inspect_agent_artifacts`, …) | `Chat/AgentControlService.swift`, `agent/src/runtime/control-tools.ts` | Absent | No | H |
| Desktop coordinator (action queue, open loops, intent routing, dispatch approvals) | `Chat/DesktopCoordinatorService.swift`, `agent/src/runtime/desktop-intent-router.ts` et al. | Absent | No | M |
| Floating-bar background-agent delegation + pill UI | `FloatingControlBar/AgentPill.swift`, `AgentDelegationExecutor.swift`, `AgentDelegationResolver.swift`, `DelegationBriefValidator.swift` | Absent | No | H |
| Multi-provider chat picker (Omi AI / Claude / Hermes / OpenClaw) + Claude OAuth connect | `Providers/AIProvider.swift`, `SettingsContentView+FloatingBarAndChat.swift`, `Chat/ClaudeAuthSheet.swift` | Absent (Windows chat is a single hosted Omi backend, no provider switch) | Partial (adapters exist in #9304, no settings UI/OAuth yet) | H |
| Structured chat content blocks (tool calls, thinking, discovery cards, agent spawn/completion cards) | `Chat/ChatContentBlockCodec.swift`, `ChatStreamingBuffer.swift` | Absent (plain markdown text bubbles only) | No | H |
| Chat attachments (image/file upload, thumbnails) | `Chat/ChatAttachment.swift` | Absent | No | M |
| Chat resources / generated artifacts (file cards, open/reveal-in-Finder, artifact lifecycle) | `Chat/ChatResource.swift`, `AgentArtifactProjection.swift` | Absent | No | M |
| Chat write-path continuity (INV-6: optimistic staging, idempotency keys, cross-surface turn projection, single apply gate) | `Chat/KernelTurnProjection.swift`, `ChatContinuityInvariants.swift` | N/A — Windows has a much simpler single-writer local-conversation model with its own last-write-merge (see below) | No | M |
| Stall detection (slow/stalled turn+tool timers, Cancel banner) | `Chat/StallDetector.swift`, `StallThresholds.swift` | Absent | No | M |
| Screen-context auto-injection into chat turns | `Chat/ScreenContextTelemetry.swift` + `ScreenContextWorkContextBuilder` | Partial — Windows always prepends a lightweight OCR snapshot (`lib/screenContext.ts`) to every chat send; no tool-mediated on-demand capture, no policy/approval layer, no telemetry taxonomy | No | M |
| Agent runtime error taxonomy + recoverable error UI | `Chat/AgentRuntimeFailure.swift`, `ChatErrorState.swift`, `AgentFailureTranscriptFormatter.swift` | Absent (Windows renders a raw `Error: <message>` bubble) | Partial (`failures.ts` ported in #9304, no UI) | L |
| Rich Omi-data + desktop tool-calling loop inside chat (SQL, memories, screen history, tasks, permissions) via `DesktopCapabilityRegistry` | `Chat/DesktopCapabilityRegistry.swift`, `ChatPrompts.swift` | Partial — Windows has a much smaller, invisible 2-iteration local-context pre-step (`lib/localAgent.ts`), not a tool-calling loop the model drives turn-by-turn | No | M |
| One-shot UI-automation planner ("type X in app Y") | N/A on Mac (superseded by full ACP agents) | **Windows-only capability**, not a gap — `lib/actionPlanner.ts` + native approval dialog | N/A | — |

---

## ACP coding-agent runtime (JSON-RPC over stdio)

- **What it is:** The mechanism that lets Omi delegate a task to an external coding agent — Claude Code, Hermes, or OpenClaw — running as a local subprocess, streaming its progress (text, thinking, tool calls, artifacts) back into Omi's chat. ACP = **Agent Client Protocol**, JSON-RPC 2.0 over stdio.
- **Where (Mac):** `desktop/macos/agent/src/adapters/acp.ts` (808 lines — `AcpRuntimeAdapter`), `adapters/hermes.ts` / `adapters/openclaw.ts` (thin subclasses), `agent/src/patched-acp-entry.mjs`, `desktop/macos/acp-bridge/dist/index.js`.
- **How it works:** `AcpRuntimeAdapter` spawns a subprocess and speaks JSON-RPC: outbound `initialize`, `session/new`, `session/resume`, `session/set_model`, `session/prompt`, `session/cancel`; inbound the subprocess sends back `session/request_permission` (resolved via `desktop-tool-policy.ts`) and `session/update` notifications, which `translateSessionUpdate` normalizes into the bridge's event stream (`agent_message_chunk`→`text_delta`, `agent_thought_chunk`→`thinking_delta`, `tool_call`/`tool_call_update`→`tool_activity`/`tool_result_display`, `plan`→`thinking_delta`). For plain Claude (`"acp"` adapter, no external `command`), it spawns `node patched-acp-entry.mjs`, which monkey-patches the npm package `@zed-industries/claude-agent-acp` (Anthropic's Claude Code CLI wrapped in ACP) to (a) apply model selection via `setModel()` after session creation and (b) intercept the Claude Agent SDK's `SDKResultSuccess` to capture real per-turn cost/token usage. A no-progress watchdog cancels external (Hermes/OpenClaw) sessions after 150s idle; the default Claude adapter has no timeout. `acp-bridge` is the local Mac-side translator between Omi's JSON-lines protocol and `claude-code-acp`; it opens a Unix socket for `omi-tools-stdio` tool relay and resolves a bundled Playwright MCP CLI.
- **Windows status:** **Absent** — repo-wide grep for `claude-agent-acp`/`agent-client-protocol`/`codingAgent` returns zero hits outside macOS.
- **PR-stack coverage:** **Yes** — PR #9304 (`feat/win-agents-1`) ports exactly this ACP adapter-core layer into `src/main/codingAgent/`.
- **Value / notes:** High. This is the flagship "delegate to Claude Code/Codex" capability. macOS-specific concern: `patched-acp-entry.mjs` and the vendored `acp-bridge/dist` are prebuilt; a Windows port needs its own build of the bridge and the Claude Code CLI on PATH (or the `@zed-industries` bridge npm dependency).

## Adapter registry / selection

- **What it is:** The layer that decides which agent backend serves a given request (Omi's own `piMono`, `acp`/Claude, `hermes`, or `openclaw`) and enforces per-adapter contracts.
- **Where (Mac):** `agent/src/runtime/adapter-registry.ts`, `adapter-selection.ts`, `adapters/interface.ts`; Swift side `Providers/AgentRuntimeRouting.swift` maps `BridgeMode`→`AgentHarnessMode`.
- **How it works:** `ADAPTER_PROFILES` maps each adapter to an activation env var — `acp` always active; `pi-mono` needs `OMI_AUTH_TOKEN`; `hermes` needs `OMI_HERMES_ADAPTER_COMMAND`; `openclaw` needs `OMI_OPENCLAW_ADAPTER_COMMAND`. `adapterIdForHarnessMode()` converts the Swift-sent harness string; `ensureRegisteredAdapter()` lazily registers on first activation. `AdapterRegistry.register()` wraps each factory in `contractCheckedAdapter()` which asserts (among other things) that Omi's `sessionId` and the adapter's native session id never collide. A per-adapter `AdapterWorkerPool` (worker-pool.ts) pins pi-mono/Hermes/OpenClaw sessions to a specific subprocess (their native ids are process-local) while native-ACP-resumable Claude bindings need no pinning; includes idle-pinned-binding eviction.
- **Windows status:** **Absent.**
- **PR-stack coverage:** **Yes** — #9304 adds an `adapterRegistry.ts`.
- **Value / notes:** High — required infrastructure for any multi-provider agent support.

## Kernel — sessions / runs / attempts / turns / artifacts

- **What it is:** The durable state machine and persistence backbone behind every agent execution — the concept that a "conversation" is an `AgentSession`, each execution is an `AgentRun` with retry-level `RunAttempt`s, producing `AgentArtifact`s, all logged as append-only `AgentEvent`s.
- **Where (Mac):** `agent/src/runtime/kernel*.ts` (kernel-core 1909 lines, kernel-coordinator, kernel-types, kernel-sessions, kernel-runs, kernel-artifacts), `sqlite-store.ts` (2206 lines, the `AgentStore` backing).
- **How it works:** Core entities: `AgentSession` (durable identity keyed by surface: `surfaceKind`/`externalRefKind`/`externalRefId`), `AgentRun` (+`RunStatus`), `RunAttempt` (+`AttemptStatus`), `AdapterBinding` (the live adapter-native session handle), `AgentArtifact` (+`ArtifactRole`/`ArtifactLifecycleState`), `AgentDelegation` (parent→child spawn records), `AgentGrant` (time-boxed capability grants from resolved approvals), `AgentEvent` (append-only log), `DesktopCoordinatorDispatch` (approval/attention items). Persisted in SQLite. Terminal statuses `{succeeded, failed, cancelled, timed_out, orphaned}`.
- **Windows status:** **Absent.**
- **PR-stack coverage:** **No** — the PR stack ports the ACP adapter/routing/UI but not the full kernel/coordinator.
- **Value / notes:** High but heavy — this is the largest, deepest part of the runtime. Windows' current chat has no equivalent durable multi-run/attempt/artifact model.

## Agent control-plane tools + Desktop Coordinator

- **What it is:** The set of tools the agent (and the app) can call to *manage other agents and drive the desktop* — list/inspect/cancel runs, spawn background agents, send messages to a running agent, inspect artifacts, plus building a "desktop awareness snapshot" (open loops, action queue, memory/task candidates) and routing an utterance to the right disposition.
- **Where (Mac):** `agent/src/runtime/control-tools.ts` + `control-tool-manifest.ts` (the Node side), `Chat/AgentControlService.swift` (voice-tool-call executor), `Chat/DesktopCoordinatorService.swift` (Swift RPC client), `agent/src/runtime/desktop-intent-router.ts`, `desktop-action-queue.ts`, `desktop-context-packet.ts`.
- **How it works:** `handleAgentControlToolCall` implements ~18 tools: `list_agent_sessions`, `get_agent_run`, `build_desktop_awareness_snapshot`, `list_desktop_action_queue`, `get_desktop_open_loops`, `build_desktop_context_packet`, `route_desktop_intent`, `evaluate_desktop_tool_policy`, `create_desktop_dispatch`, `resolve_desktop_dispatch`, `cancel_agent_run`, `inspect_agent_artifacts`, `update_agent_artifact_lifecycle`, `send_agent_message`, `spawn_background_agent`, `spawn_agent`, `run_agent_and_wait`, `set_desktop_attention_override`. Every Swift `DesktopCoordinatorService` method is a thin wrapper over these. `routeDesktopIntent()` classifies an utterance into `quick_answer`/`resume`/`fork`/`delegate`/`dispatch`/`new_run` via regex heuristics + session-candidate relevance scoring (threshold 0.55). Resolving a dispatch can mint an `AgentGrant` with strict capability/operation/resource/expiry matching.
- **Windows status:** **Absent.**
- **PR-stack coverage:** **No.**
- **Value / notes:** High for the "agent that manages agents / drives the app" vision; not needed for a basic single-agent delegate.

## Desktop tool-policy engine

- **What it is:** A capability-bundle permission engine that decides whether a tool call is allowed, denied, or needs user approval — the backstop for ACP `session/request_permission`.
- **Where (Mac):** `agent/src/runtime/desktop-tool-policy.ts` (374 lines).
- **How it works:** Tools are tagged with a `DesktopCoordinatorBundle` (11 bundles, e.g. `desktop.agent_control.manage`, `desktop.context.screenshot_image`, `external.write_send`), a `riskTier` (low/medium/high), a `privacyTier` (low/local_private/sensitive), and an `approvalPolicy` (allow/user_approval/policy_grant/deny), producing a `DesktopToolPolicyDecision` of allow/deny/dispatch_required. `resolveAcpPermission`/`resolveExternalAcpPermission` call into this from `acp.ts` when a subprocess requests a permission.
- **Windows status:** **Absent** (Windows' one automation path uses a single native approval dialog per action, no bundle/risk/privacy taxonomy).
- **PR-stack coverage:** **Partial** (`failures.ts`-adjacent policy bits may come with #9304; the full engine does not).
- **Value / notes:** Medium — matters once agents can take consequential local/external actions.

## Floating-bar background-agent delegation + AgentPill

- **What it is:** From the floating bar you say "spawn an agent to fix the failing test in my repo" (or "spawn 3 agents…") and Omi launches background agents, each surfaced as a live **pill** card showing status (queued→running→done), with voice/text follow-up, stop, and dismiss.
- **Where (Mac):** `FloatingControlBar/AgentPill.swift` (2195 lines — `AgentPill` model + `AgentPillsManager`), `AgentDelegationExecutor.swift`, `AgentDelegationResolver.swift`, `DelegationBriefValidator.swift`, `AgentPill`/`AgentProviderLogoMark`.
- **How it works:** `AgentPillsManager.spawnFromUserQuery` parses agent-count ("spawn 3 agents"), provider directives ("ask hermes to…", "openclaw: …") via regex, then calls `DesktopCoordinatorService.spawnAgent(...)` (the same canonical spawn path `ChatToolExecutor.executeSpawnAgent` uses). Each pill runs a `pollCanonicalRun` loop hitting `inspectAgentRun(runId:)` every 2s, mapping kernel run status onto its `Status` enum (queued/starting/running/done/stopped/failed, hardcoded tint colors). Follow-ups (`continueAgent`) cancel the active run then re-prompt; attachments on follow-ups are passed by local file path (floating agents run locally with disk access, no upload). Max 8 pills. Finished runs' artifacts convert to `ChatResource.artifact(...)`. Spawn is blocked in Ask mode and blocked when the caller is itself a floating-pill agent (no nested self-spawn). A Haiku classifier routes chat-vs-agent.
- **Windows status:** **Absent.**
- **PR-stack coverage:** **No** (routing exists in the stack, but not the pill UI/delegation UX).
- **Value / notes:** High — this is the most visible, differentiated agent UX.

## Multi-provider chat picker + Claude OAuth + BridgeMode

- **What it is:** A user-facing switch between chat backends — Omi AI (`piMono`), Claude (your own Claude subscription via OAuth), Hermes, OpenClaw — persisted and hot-swappable.
- **Where (Mac):** `Providers/ChatProvider.swift` (`BridgeMode` enum, `switchBridgeMode`), the picker UI in `ChatPage.swift`/`SettingsContentView+FloatingBarAndChat.swift`, `Chat/ClaudeAuthSheet.swift`, and the OAuth machinery in `agent/src/oauth-flow.ts`.
- **How it works:** `BridgeMode` = `.omiAI`(legacy→piMono) / `.userClaude` / `.piMono` / `.hermes` / `.openClaw`, `@AppStorage("chatBridgeMode")`. `switchBridgeMode` serializes overlapping switches, fully stops the old Node bridge (`stopAndWaitForExit`), recreates the `AgentClient` session for the new harness, and warms it. `oauth-flow.ts` is a standalone reimplementation of Claude Code's `setup-token` PKCE flow: local callback server → browser `claude.ai/oauth/authorize` → token exchange → **credentials stored in the macOS Keychain** (`security add-generic-password`, service `"Claude Code-credentials"`). Note: `ClaudeAuthSheet.swift` (despite the name) is actually a generic "Upgrade to Omi Pro" paywall sheet in the read build path — it sends the user to `omi.me/pricing` and reverts to piMono; the real Claude OAuth is triggered by `isClaudeAuthRequired`+`claudeAuthUrl` opening the browser, with the Node bridge doing the token exchange.
- **Windows status:** **Absent** — Windows chat is a single hosted Omi backend (piMono-equivalent), no provider switch, no Claude connect.
- **PR-stack coverage:** **Partial** — #9304 ports the adapters, but no settings UI / OAuth flow yet.
- **Value / notes:** High. macOS-specific: Keychain credential storage needs a Windows Credential Manager / DPAPI equivalent.

## Structured chat content blocks

- **What it is:** Rich in-message rendering beyond plain text — tool-call cards, thinking blocks, discovery cards, agent-spawn cards, agent-completion cards — driven by a typed content-block stream.
- **Where (Mac):** `Chat/ChatContentBlockCodec.swift`, `ChatStreamingBuffer.swift`; rendered in `ChatBubble.swift`/`AIResponseView.swift` (`ToolCallsGroup`, `ThinkingBlock`, `DiscoveryCard`, `AgentSpawnCard`, `AgentCompletionCard`). Post-stream filtering drops `.thinking` blocks and keeps only tool-call groups that spawned an agent.
- **How it works:** The bridge emits typed deltas (text/thinking/toolCall/toolResult); the codec assembles them into `contentBlocks` per message; while streaming everything renders, and once complete non-agent tool calls are pruned from the transcript.
- **Windows status:** **Absent** — Windows `ChatMessages.tsx` renders plain markdown text bubbles only (a `think:`-prefixed line is simply dropped, no thinking UI; no tool-call/discovery/agent cards).
- **PR-stack coverage:** **No.**
- **Value / notes:** High for agent transparency (seeing what the agent is doing).

## Chat attachments (image / file upload)

- **What it is:** Attaching images/files to a chat message (drag-drop), with previews and server-side upload so the agent can see them.
- **Where (Mac):** `Chat/ChatAttachment.swift`; staged in `ChatProvider.pendingAttachments`, uploaded via `awaitPendingUploads()` before send; first image's bytes become `imageBase64` to the bridge.
- **How it works:** Drag-drop of `fileURL` → `ChatAttachment.from(url:)`, capped by `kMaxChatAttachments`, previewed in `AttachmentPreviewRow`; send blocks on upload to embed `serverId`s.
- **Windows status:** **Absent.**
- **PR-stack coverage:** **No.**
- **Value / notes:** Medium.

## Chat resources / generated artifacts

- **What it is:** When an agent produces files (code, docs), they appear as resource cards you can open / reveal, with lifecycle tracking.
- **Where (Mac):** `Chat/ChatResource.swift`, `AgentArtifactProjection.swift`; Node side `agent/src/runtime/artifact-storage.ts` (`OmiArtifactStorage`), `artifact-serialization.ts`, `artifact-filters.ts`.
- **How it works:** Adapter-produced files are normalized/copied into a managed root, hashed, filename-sanitized, manifested; serialized over the JSONL transport into Swift's `AgentArtifactProjection`, rendered as a `ChatResourceStrip`.
- **Windows status:** **Absent.**
- **PR-stack coverage:** **No.**
- **Value / notes:** Medium — needed for coding-agent output to be useful.

## Chat write-path continuity (INV-6)

- **What it is:** The invariant that a chat turn is written exactly once and consistently across surfaces (main chat, floating bar, voice), via optimistic staging then canonical promotion under a single idempotency key.
- **Where (Mac):** `Chat/KernelTurnProjection.swift`, `ChatContinuityInvariants.swift`, and `ChatProvider`'s `pendingSurfaceTurns` + `stageOptimisticTurn`/`promoteOptimisticTurn`/`hasOptimisticTurn`.
- **How it works:** `stageOptimisticTurn(continuityKey:…)` idempotently upserts optimistic user+assistant rows (assistant text defaults to "Done." for pure tool/artifact turns); when the kernel's canonical `KernelTurnRecorded` arrives, `promoteOptimisticTurn` replaces the staged text in place (never appends). This is the concrete mechanism behind the documented INV-6 rule.
- **Windows status:** **N/A / much simpler** — Windows has a single-writer local-conversation model (`lib/chatConversation.ts`) with its own last-write-merge; it does not need cross-surface projection because it has one surface.
- **PR-stack coverage:** **No.**
- **Value / notes:** Medium — only becomes relevant if Windows gains multiple concurrent chat surfaces (bar + main + voice) writing to one history.

## Stall detection

- **What it is:** Detecting when an agent turn or a tool call has gone slow/stalled and surfacing a "slow…"/"stalled — Cancel?" affordance.
- **Where (Mac):** `Chat/StallDetector.swift`, `StallThresholds.swift`; one detector per query, fed on every text delta and tool start/complete.
- **How it works:** `StallDetector(thresholds: .v1Defaults)` `.step(kind:atMs:)` returns transitions mapped to banner/tool-status state; a 180s watchdog in `sendMessage` force-interrupts a fully-hung bridge (known cause: stale ACP subprocess after machine sleep).
- **Windows status:** **Absent** (Windows relies on a single post-release 25s PTT watchdog and raw error text).
- **PR-stack coverage:** **No.**
- **Value / notes:** Medium — quality-of-life for long agent runs.

## Screen-context auto-injection into chat

- **What it is:** Automatically attaching a snapshot of what's on screen (or recent activity) to a chat turn so the assistant is grounded in current context.
- **Where (Mac):** `Chat/ScreenContextTelemetry.swift` + `ScreenContextWorkContextBuilder`; injected in `ChatProvider.sendMessage`.
- **How it works:** If `ScreenContextAutoIncludePolicy.reason(...)` fires, checks `CGPreflightScreenCaptureAccess()` (ambient requests silently skip if not granted; explicit "what's on my screen" proceed so the model can report the missing permission), builds `get_work_context` payload (minutes:10), wraps it in `<auto_screen_context>` XML in the system prompt, and records synthetic tool telemetry so analytics see it as a tool use.
- **Windows status:** **Partial** — Windows *always* prepends a lightweight OCR snapshot (`lib/screenContext.ts`, cache-first with fast→slow fallback, 4000-char cap) to every send. It lacks the eligibility policy, the tool-mediated on-demand capture, the permission-aware skip, and the telemetry taxonomy.
- **PR-stack coverage:** **No.**
- **Value / notes:** Medium — Windows has the core value; the gap is precision/policy.

## Agent error taxonomy + recoverable-error UI

- **What it is:** Structured, sanitized agent failures with user-friendly messages and recovery affordances, instead of a raw error string.
- **Where (Mac):** `agent/src/runtime/failures.ts` (168 lines, the source of truth), `Chat/AgentRuntimeFailure.swift`, `ChatErrorState.swift`, `AgentFailureTranscriptFormatter.swift`.
- **How it works:** `RuntimeFailure{code, userMessage, technicalMessage, source, adapterId, provider, retryable}`; `sanitizeProcessDiagnostic()` redacts Bearer tokens / API keys / `sk-` secrets from stderr before surfacing; adapter-specific classification (e.g. OpenClaw config-invalid via stderr sniffing). Swift maps this to `ChatErrorState` with structured recovery (e.g. auth-required preserves the user's draft text).
- **Windows status:** **Absent** — Windows renders a raw `Error: <message>` bubble.
- **PR-stack coverage:** **Partial** — `failures.ts` is ported in #9304, but no UI.
- **Value / notes:** Low-Medium.

## Rich Omi-data + desktop tool-calling loop inside chat

- **What it is:** In chat, the model can call ~40 tools — read-only SQL over the local Rewind DB, semantic search over screenshots, tasks/memories/conversations, screen capture, calendar, onboarding tools, even `point_click` desktop control — driven turn-by-turn by the model.
- **Where (Mac):** `Chat/ChatToolExecutor.swift` (2116 lines — the text-chat client-tool executor), `Chat/DesktopCapabilityRegistry.swift`, `agent/src/runtime/omi-tool-manifest.ts` (1541 lines), `omi-tools-http.ts`/`omi-tools-stdio.ts`.
- **How it works:** `execute(_:)` switches over `GeneratedToolExecutors.chatDispatch` plus special-cased `spawn_agent`. Every call first passes `localPolicyDecision` (e.g. `execute_sql` denied unless read-only per a hand-rolled SQL tokenizer; `capture_screen` gated by a user setting *and* `CGPreflightScreenCaptureAccess()`). Local tools hit the local `omi.db`; backend RAG/calendar tools call `APIClient.tool*` → Python `/v1/tools/*`. Result formatting is three families: plain strings, prefixed+JSON for policy/permission failures (`POLICY_DENIED:`/`PERMISSION_REQUIRED:`), and raw JSON.
- **Windows status:** **Partial** — Windows has `lib/localAgent.ts`, a much smaller *invisible* 2-iteration local-context pre-step (an `execute_sql` enrichment loop) that is currently **turned OFF** in code ("Floor-only mode… enrichment is OFF"), not a model-driven turn-by-turn tool loop. No `point_click`/screen-control tools.
- **PR-stack coverage:** **No.**
- **Value / notes:** Medium-High — the tool loop is what makes Omi chat "agentic" over the user's own data.

## ChatProvider orchestration + warmup (architecture)

- **What it is:** The single `@MainActor` orchestrator behind every chat surface (main / floating / task chat / agent pill), distinguished at runtime by `ChatTurnOwner` rather than separate classes.
- **Where (Mac):** `Providers/ChatProvider.swift` (5402 lines).
- **How it works:** `sendMessage` guards single-in-flight, checks free-tier quota, arms a 180s watchdog, uploads attachments, persists the user message, appends optimistic rows, builds the system prompt (or reuses the cached one), resolves an `AgentSurfaceReference`, and calls `AgentClient.query(...)` with streaming callbacks. `ensureBridgeStarted` is the warmup path: it builds/caches three system prompts (main, floating, floating-pill — the pill prompt excludes `spawn_agent`/`run_agent_and_wait`) and pre-warms two ACP sessions ("main","floating") so the first query pays no session-creation latency. Notably, conversation history + coordinator route + context packet are assembled by the Node **kernel** at query time, not by Swift — less prompt logic lives in Swift than expected.
- **Windows status:** **Present-but-simpler** — `hooks/useChat.ts` + `lib/chatConversation.ts` is a single-surface streaming chat; no warmup/session-caching, no multi-owner projection.
- **PR-stack coverage:** **No.**
- **Value / notes:** Architectural context for anyone porting the runtime.

## pi-mono provider (the "Omi AI" baseline)

- **What it is:** Omi's own built-in assistant — the equivalent of what Windows chat already is.
- **Where (Mac):** `agent/src/adapters/pi-mono.ts` (1041 lines), `desktop/macos/pi-mono-extension/` (`omi-provider`).
- **How it works:** Spawns the bundled `@mariozechner/pi-coding-agent` CLI in RPC mode with `--provider omi --model omi-sonnet` plus a custom `pi-mono-extension` (registers Omi's backend as the LLM provider and enforces a dangerous-command denylist before tool execution). Auth requires a Firebase ID token mapped to `OMI_API_KEY` (explicitly refuses `ANTHROPIC_API_KEY` — the Omi backend rejects provider keys). Talks to `api.omi.me`, not directly to any LLM provider. System prompt is baked at spawn (changing it requires a subprocess restart).
- **Windows status:** **Present (equivalent)** — Windows chat is functionally the piMono/hosted-Omi lane.
- **PR-stack coverage:** N/A (baseline).
- **Value / notes:** Confirms Windows already has the "Omi AI" tier; the gap is the *other* providers + the agent runtime around them.

## agent-cloud (hosted always-on agent VM)

- **What it is:** A separate cloud-hosted variant of the agent that runs on a per-user VM (the `agent-proxy` → `ws://<ip>:8080/ws` flow in the backend service map) for always-on / remote use.
- **Where (Mac):** `desktop/macos/agent-cloud/agent.mjs` + `package.json` (`omi-agent-cloud`).
- **How it works:** A long-lived Node WebSocket/HTTP server built directly on `@anthropic-ai/claude-agent-sdk` (not ACP), with a local SQLite DB synced from the desktop over an allowlisted `SYNC_TABLES` set (screenshots, action_items, transcription sessions/segments, memories, staged_tasks, focus_sessions, observations, live_notes, ai_user_profiles). Exposes `execute_sql`, `semantic_search`, `get_daily_recap`, Playwright browser tools, and backend tools; 30-min idle auto-stop. Self-contained — does not share `agent/src`'s kernel/adapter code.
- **Windows status:** **Absent** (and is a backend/VM concern more than a client one).
- **PR-stack coverage:** **No.**
- **Value / notes:** Low for the desktop client itself; noted for completeness.

## Chat Lab (internal dev tool — NOT a user feature)

- **What it is:** An internal prompt-engineering evaluation harness (prompt version history from git, prompt editor, canned-question eval with AI grading). Contains a hardcoded developer path (`/Users/nik/projects/omi`) and requires the user's own Anthropic key.
- **Where (Mac):** `MainWindow/Pages/ChatLabView.swift` (1121 lines).
- **Windows status:** **N/A** — not a shippable feature; explicitly out of scope for parity. Listed only so it isn't mistaken for a user-facing gap.

---

## Spotted outside my scope

- `ChatLabView` hardcodes a specific developer's machine path and is an internal-only tool (no end-user value).
- `ClaudeAuthSheet.swift` is a naming mismatch — it's a Pro-upgrade paywall sheet, not the Claude-OAuth UI.
- Swift computes and forwards `OMI_BYOK_*` env vars into the Node subprocess, but no code path in `agent/src` was found to consume them — possibly not-yet-wired, dead, or consumed in `pi-mono-extension/` (open question).
- `local-subprocess.ts` / `one-shot-cli.ts` in `agent/src` were not fully read — unclear if dead code or test-only.
- The Windows-only one-shot UI-automation planner (`lib/actionPlanner.ts` + native approval dialog) has no Mac equivalent — a Windows *advantage*, not a gap.
- Whether the Windows backend even sends citation metadata to the client (relevant to the citation-card gap in the UI audit) is a backend-contract question, not a client one.
