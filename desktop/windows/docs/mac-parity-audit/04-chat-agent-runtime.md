# Mac→Windows Parity Audit — Chat + Agent Runtime (ACP)

> **Re-audited 2026-08-22.** Scope unchanged from the 2026-08-20 pass: the macOS desktop app's
> chat surface plus its full agent-runtime stack — the Node.js coding-agent runtime (ACP
> JSON-RPC over stdio), the "kernel" (sessions/runs/attempts/turns/artifacts), the desktop agent
> control plane, floating-bar background-agent delegation, and chat depth (attachments,
> resources/artifacts, continuity, screen-context injection, stall detection, Claude auth).
> Windows baseline re-checked directly against source: `desktop/windows/src/main/agentKernel/**`,
> `src/main/codingAgent/**`, `src/main/ipc/{agentControl,codingAgent,agentCards}.ts`,
> `src/renderer/src/hooks/{useChat,useAgentPills,useCodingAgents}.ts`,
> `src/renderer/src/components/{chat,bar}/**`, `src/renderer/src/lib/{localAgent,screenContext,
> agentTask,chatAttachments,claudeSignIn}.ts`, `src/shared/{types,chatContent}.ts`, plus
> `git log`/`git blame` on all of the above to date every claim against 2026-08-20.
>
> **Headline correction: the previous pass was not "stale in places" here — it was wrong about
> the central claim of the whole file.** The 2026-08-20 audit asserted the ACP kernel,
> control-plane, and agent-pill UX "do not exist as PRs yet" and that Windows chat is "a single
> hosted Omi backend, no provider switch." Both were false **on the date the audit was written**:
> `desktop/windows/src/main/agentKernel/` (57 files) and `src/main/codingAgent/` (33 files) were
> merged to `main` in five waves between **2026-07-11 and 2026-07-29** — three to six weeks before
> the audit — and two more commits landed **2026-08-09/2026-08-20**, the audit's own date. This
> reads as the 00-INDEX grep methodology (`grep -r 'codingAgent|claude-agent-acp|...'`) having been
> run against a stale checkout, or the PR-stack framing ("#9304 not yet merged") never having been
> revisited once the stack actually landed on `main` under different branch names. See
> [PARALLEL-PLAN.md](PARALLEL-PLAN.md) Stream 1 for the follow-on work this correction was already
> based on — that plan is treated as ground truth here too, and was itself re-verified against
> current source below, not just cited.

## Changed since the 2026-08-20 audit

Every row below is a status *flip* from the old file, re-verified against current source — not
a restatement of what PARALLEL-PLAN.md/WIRING-AUDIT.md already said, though this rewrite agrees
with both where they overlap.

| Item | Old audit said | Actually (2026-08-22) |
|---|---|---|
| ACP coding-agent client | Absent; PR #9304 "ports this" (future tense) | **Shipped and has been for ~5 weeks.** `codingAgent/acp.ts` (1128 lines) landed 2026-07-11, last touched 2026-07-20. Watchdog, permission resolution, `translateSessionUpdate` all present, faithfully mirroring the Mac mechanism the old audit described. |
| Adapter registry | Absent | **Shipped**, in two layers: `codingAgent/adapterRegistry.ts` (149 lines, activation/env-var profiles) + `agentKernel/adapterRegistry.ts` (95 lines, contract-checked wrapper asserting the session-id-collision invariant) — landed 2026-07-14. |
| Kernel (sessions/runs/attempts/artifacts, SQLite) | Absent; "largest, deepest part of the runtime," "no PR" | **Shipped.** `agentKernel/store.ts` (2841 lines, 25 tables), `kernelCore.ts` (2252 lines), `kernelRuns.ts`, `kernelSessions.ts`, `kernelArtifacts.ts` — landed 2026-07-14, still receiving fixes through 2026-07-29. `resumeBinding` (flagged by PARALLEL-PLAN as "modeled but never called" on 2026-07-13) is now called for real at `kernelCore.ts:1159`. |
| Agent control-plane tools + coordinator | Absent | **Shipped**, name-for-name identical to the Mac tool list the old audit itself cited: all 18 tools present in `controlTools.ts` (1423 lines) with the exact same names (`list_agent_sessions` … `set_desktop_attention_override`), wired live via `main/ipc/agentControl.ts` → `registerAgentControlIpc()` in `main/index.ts:1014`. |
| Desktop tool-policy engine | Absent | **Shipped.** `desktopToolPolicy.ts` (412 lines): 12 capability bundles (not Mac's 11 — Windows added one), risk/privacy/approval tiers, deny-by-default, resolves both control tools and the ~31-entry product-tool manifest (`omiToolManifest.ts`, 1750 lines). |
| Floating-bar AgentPill UX | Absent; "most visible, differentiated agent UX," no PR | **Shipped.** `AgentPillView.tsx` + `useAgentPills.ts` (310 lines) landed 2026-07-19 (commit tagged "B3"), 2s poll cadence matching Mac's `AgentPill.swift:1775` exactly, viewed-TTL eviction, idle-heartbeat backoff to 30s when no pills are active. |
| Multi-provider settings UI + Claude OAuth | Absent / no UI | **Shipped.** `AgentsTab.tsx`: PATH auto-detection, one-click Connect + real ACP handshake test per external agent (OpenClaw/Hermes/Codex), a Codex OpenAI-key lane, and Claude Code OAuth (`claudeOAuth.ts`, 490 lines, PKCE loopback writing the SDK-native `.credentials.json` — same file format Claude Code's own CLI reads, so no Keychain-equivalent is even needed). |
| Chat attachments | Absent | **Shipped.** `chatAttachments.ts` (154 lines) + `ChatAttachmentStrip.tsx` (132 lines): drag-drop, upload, image/document cards rendered above the bubble, wired into `useChat.ts`'s send path. |
| C4 (done-payload discard) | Listed as a live Critical in WIRING-AUDIT | **Confirmed fixed**, independently re-verified: `useChat.ts:1290-1293` stores `serverId`/`citations`/`chartData`/`askForNps` from the terminal frame. |
| C5 (no abort path) | Listed as a live Critical in WIRING-AUDIT | **Confirmed fixed**, independently re-verified: `AbortController` (`useChat.ts:278`, `:1118-1128`) + generation counter + a 180s watchdog (`CHAT_STREAM_TIMEOUT_MS`, `:75`) torn down together on `reset()`. |
| Default chat engine | "Windows chat is a single hosted Omi backend" | Default chat is **already routed through the kernel's `pi_mono` adapter** — `useChat.ts` comments call it "now the default" (`:645`, `:1080`) — ahead of PARALLEL-PLAN's own decision-gate #8, which had this staged behind a flag as a *future* milestone. Worth a product gate-check: is this intentional-and-shipped, or did the flag default flip by accident before the gate's required safeguards (fallback telemetry, continuity guard test) were confirmed in place? Not re-verified here — flagged for the sequencing-plan owner. |
| Structured content blocks | Absent (plain markdown only) | **Partially shipped**, upgraded from "types-only stub" to "one real card type wired end to end": `agentSpawn`/`agentCompletion` blocks render as `AgentThreadCard` in both the main window and the bar. `toolCall`/`thinking`/`discoveryCard` block types exist in `shared/chatContent.ts` but still have zero rendering consumers — genuinely unchanged from the old audit for those three kinds. |
| Chat resources / artifacts | Absent | **Still absent in the UI**, but for a different reason than before: the `ChatResource` type is published (`shared/chatContent.ts`) and the kernel-side artifact machinery is real and used (`artifactStorage.ts`, `kernelArtifacts.ts`, `serializeArtifact` in `controlTools.ts`) — there is simply no chat-surface card component consuming it yet. Old audit's "Absent" verdict was already correct for the UI layer; it just didn't know the backend half now exists. |
| Screen-context auto-injection | Partial, OCR-text prepend | **Unchanged** — confirmed genuinely stale-free: `git log` on `screenContext.ts` shows zero commits since the 2026-06-11 repo split. Old audit's characterization stands verbatim. |
| Stall detection | Absent | **Unchanged, confirmed still absent.** No stall-detector files exist; only the coarse 180s hard watchdog (shared with C5's fix) exists, same as before. |
| `localAgent.ts` enrichment loop | Partial, `ENRICH_ENABLED = false` | **Unchanged** — still `false` at `localAgent.ts:33`, though the file was touched 2026-08-09 for an unrelated managed-structured-lane change; the flag itself was not flipped. |

Net: of the 15 feature rows in the original summary table, **9 flip from Absent/Partial to
Present**, 1 flips from a stale "no abort path" framing to confirmed-fixed, 1 gains a materially
different (and more positive) mechanism description without changing status (Claude auth
storage), and 4 are confirmed genuinely unchanged (screen-context, stall detection, structured
non-agent content blocks, enrichment loop). This is the single largest correction in the whole
parity audit re-pass to date.

## Summary table

| Feature | Mac location(s) | Windows status (2026-08-22) | Value (H/M/L) |
|---|---|---|---|
| ACP JSON-RPC coding-agent client (spawn Claude Code/Codex/Hermes/OpenClaw over stdio) | `agent/src/adapters/acp.ts`, `acp-bridge/` | **Present** — `src/main/codingAgent/acp.ts` (1128 lines) + `hermes.ts`/`openclaw.ts`/`codex.ts` + `claude-acp-entry.mjs`, landed 2026-07-11→07-20 | H |
| Adapter registry / selection | `agent/src/runtime/adapter-registry.ts`, `adapter-selection.ts` | **Present** — `codingAgent/adapterRegistry.ts` + `agentKernel/adapterRegistry.ts` (contract-checked), 2026-07-14 | H |
| Kernel: sessions/runs/attempts/turns/artifacts in SQLite | `agent/src/runtime/kernel*.ts`, `sqlite-store.ts` | **Present** — `agentKernel/store.ts` (2841 lines, 25 tables), `kernelCore.ts` (2252 lines), `kernelRuns.ts`, `kernelSessions.ts`, `kernelArtifacts.ts`, `kernelTypes.ts` | H |
| Agent control-plane tools (18, name-for-name match) | `Chat/AgentControlService.swift`, `agent/src/runtime/control-tools.ts` | **Present** — `agentKernel/controlTools.ts` (1423 lines), wired via `main/ipc/agentControl.ts` | H |
| Desktop coordinator (action queue, open loops, intent routing, dispatch approvals) | `Chat/DesktopCoordinatorService.swift`, `desktop-intent-router.ts` et al. | **Present** — `desktopIntentRouter.ts`, `desktopActionQueue.ts`, `desktopContextPacket.ts`, called from `kernelCore.ts` and exposed as control tools | M |
| Desktop tool-policy engine | `agent/src/runtime/desktop-tool-policy.ts` | **Present** — `desktopToolPolicy.ts` (412 lines), 12 bundles, deny-by-default, product-tool manifest resolution | M |
| Floating-bar background-agent delegation + pill UI | `FloatingControlBar/AgentPill.swift`, `AgentDelegationExecutor.swift` | **Present** — `AgentPillView.tsx`, `useAgentPills.ts` (310 lines), `agentPills.ts`, `agentPillTranscript.ts`, landed 2026-07-19 | H |
| Multi-provider agent connect (Claude/OpenClaw/Hermes/Codex) + Claude OAuth | `Providers/AIProvider.swift`, `Chat/ClaudeAuthSheet.swift` | **Present, different shape** — `AgentsTab.tsx` settings UI + `claudeOAuth.ts` (490 lines, SDK-native credentials file). Not an app-wide "BridgeMode" chat-backend picker like Mac's — provider selection happens per-message via mention-detection (`agentTask.ts`) or the model's own `spawn_agent` tool call, not a persistent toggle | H |
| Structured chat content blocks | `Chat/ChatContentBlockCodec.swift`, `ChatStreamingBuffer.swift` | **Partial** — `agentSpawn`/`agentCompletion` render as `AgentThreadCard`; `toolCall`/`thinking`/`discoveryCard` types exist in `shared/chatContent.ts` with zero renderers | H |
| Chat attachments (image/file upload, thumbnails) | `Chat/ChatAttachment.swift` | **Present** — `chatAttachments.ts` + `chatAttachmentUpload.ts` + `ChatAttachmentStrip.tsx`, non-interactive cards (no open/reveal, by design note in the file) | M |
| Chat resources / generated artifacts (file cards, open/reveal, lifecycle) | `Chat/ChatResource.swift`, `AgentArtifactProjection.swift` | **Absent in UI, backend half exists** — `ChatResource` type published, `artifactStorage.ts`/`kernelArtifacts.ts` real and used by agent runs, but no chat-surface card renders them | M |
| Chat write-path continuity | `Chat/KernelTurnProjection.swift`, `ChatContinuityInvariants.swift` | **Present, Windows-specific mechanism** — `lib/chat/agentThreadCards.ts` (`mergeAgentCards`, tagged "INV-CHAT-1" in-code) does the single-surface equivalent: kernel-authoritative agent cards merged into the one local thread by `chatId` match, not a multi-surface optimistic-staging protocol (Windows still has one surface, so it doesn't need one) | M |
| Stall detection (slow/stalled turn+tool timers, Cancel banner) | `Chat/StallDetector.swift`, `StallThresholds.swift` | **Absent** — unchanged; only the coarse 180s hard watchdog exists | M |
| Screen-context auto-injection into chat turns | `Chat/ScreenContextTelemetry.swift` | **Partial, unchanged** — `screenContext.ts` (36 lines) always prepends OCR text; zero commits since the 2026-06-11 repo split | M |
| Agent runtime error taxonomy + recoverable error UI | `agent/src/runtime/failures.ts`, `ChatErrorState.swift` | **Partial, more than before** — `codingAgent/failures.ts` (238 lines) ported; `chatErrorCopy.ts` maps raw errors to plain-English copy (401→"sign in", 429→busy-not-your-fault) so the old audit's "raw `Error: <message>` bubble" claim no longer holds, but there's no dedicated recovery-CTA UI (retry/sign-in button) matching Mac's five-state `ChatErrorState` | L-M |
| Rich Omi-data + desktop tool-calling loop inside chat | `Chat/ChatToolExecutor.swift`, `DesktopCapabilityRegistry.swift` | **Partial, unchanged** — `localAgent.ts` still has `ENRICH_ENABLED = false` (line 33); the real turn-by-turn model-driven loop exists as the MCP/relay bridges (`controlMcpBridge.ts`, `toolRelayBridge.ts`) that a spawned coding agent can use, but the *default chat's own* local-context enrichment step is still the same disabled 2-iteration pre-step the old audit found | M-H |
| One-shot UI-automation planner ("type X in app Y") | N/A on Mac | **Windows-only capability, unchanged** — `lib/actionPlanner.ts` + native approval dialog | — |

---

## ACP coding-agent runtime (JSON-RPC over stdio)

- **What it is:** The mechanism that lets Omi delegate a task to an external coding agent —
  Claude Code, OpenClaw, Hermes, or Codex — running as a local subprocess, streaming its progress
  back into Omi's chat. ACP = **Agent Client Protocol**, JSON-RPC 2.0 over stdio.
- **Where (Mac):** `desktop/macos/agent/src/adapters/acp.ts` (808 lines), `adapters/hermes.ts` /
  `adapters/openclaw.ts`, `agent/src/patched-acp-entry.mjs`, `acp-bridge/dist/index.js`.
- **Where (Windows, current):** `src/main/codingAgent/acp.ts` (1128 lines), `hermes.ts` (20
  lines, thin subclass), `openclaw.ts` (19 lines, thin subclass), `codex.ts` (34 lines — a fourth
  external adapter Windows added that the old audit's Mac-side feature list did not carry;
  worth a note back to whoever maintains the Mac audit rows, since it means Windows' external-agent
  set is now a superset of what was documented, not a subset), `claude-acp-entry.mjs` (Windows'
  equivalent of `patched-acp-entry.mjs`), `agentDetect.ts`/`agentConfigDir.ts` (PATH detection +
  config-dir resolution), plus `acp.testkit.ts` and 6 dedicated ACP test files including
  `acp.e2e.test.ts` and `acp.integration.test.ts`.
- **How it works (verified against current source, not just the old citation):** Same shape as
  the Mac mechanism the old audit described — `initialize`/`session/new`/`session/prompt`/
  `session/cancel` outbound, `session/request_permission` + `session/update` inbound. A
  no-progress watchdog (`DEFAULT_EXTERNAL_NO_PROGRESS_TIMEOUT_MS = 150_000`, `acp.ts:236`) cancels
  external (Hermes/OpenClaw/Codex) sessions after 150s idle, matching Mac's 150s constant exactly;
  the code comment at `acp.ts:237` explicitly notes the first-party Claude Code bridge has no such
  timeout, again matching Mac. Permission resolution and cancellation-during-watchdog handling
  (`acp.ts:722-836`) are both present with explicit "not silent" comments about the watchdog's
  guarantee.
- **Landed:** `git log` shows `acp.ts` added 2026-07-11 (`vendor(windows): copy codingAgent/**
  ACP adapter core from karthik/win-agents-4-polish`) with fixes through 2026-07-20 — i.e. it was
  already a month old and on `main` when the 2026-08-20 audit was written.
- **Value / notes:** High, and no longer a gap. Remaining Windows-specific concern from the old
  audit (needing its own bridge build / Claude Code CLI on PATH) is resolved in practice —
  `agentDetect.ts` does PATH auto-detection and `AgentsTab.tsx` surfaces install guidance per
  external agent.

## Adapter registry / selection

- **What it is:** The layer that decides which agent backend serves a given request and enforces
  per-adapter contracts.
- **Where (Mac):** `agent/src/runtime/adapter-registry.ts`, `adapter-selection.ts`.
- **Where (Windows, current):** Two layers, matching the Mac split more closely than the old
  audit's single-bullet framing suggested: `codingAgent/adapterRegistry.ts` (149 lines) handles
  activation-env-var profiles per adapter; `agentKernel/adapterRegistry.ts` (95 lines) wraps each
  factory in a contract check (`assertAdapterBindingContract`) asserting Omi's `sessionId` and the
  adapter's native session id never collide — the exact invariant the old audit cited from Mac's
  `contractCheckedAdapter()`.
- **Landed:** 2026-07-14 (`feat(windows): agent-kernel adapter layer + foundation modules (PR
  3a)`).
- **Value / notes:** High. No longer a gap.

## Kernel — sessions / runs / attempts / turns / artifacts

- **What it is:** The durable state machine and persistence backbone behind every agent
  execution.
- **Where (Mac):** `agent/src/runtime/kernel*.ts` (kernel-core 1909 lines), `sqlite-store.ts`
  (2206 lines).
- **Where (Windows, current):** `agentKernel/store.ts` (2841 lines — larger than Mac's
  `sqlite-store.ts`), `kernelCore.ts` (2252 lines — also larger than Mac's kernel-core),
  `kernelRuns.ts`, `kernelSessions.ts`, `kernelArtifacts.ts`, `kernelTypes.ts`, `kernelSupport.ts`,
  `kernel.ts` (329 lines, the public API facade), backed by a dedicated `omi-agentd.sqlite3`
  (per the 2026-07-14 commit message: "port agent-kernel SQLite store (22 tables, dedicated
  omi-agentd.sqlite3)"; a direct `grep -c "CREATE TABLE"` against current `store.ts` counts 25 —
  plausibly a few tables were added after that commit's message was written, or some are indexes
  on split tables; either way substantially the full schema, not a subset).
- **How it works:** Same entity model the old audit described from Mac (`AgentSession`,
  `AgentRun`/`RunAttempt`, `AdapterBinding`, `AgentArtifact`, `AgentDelegation`, `AgentEvent`) —
  `kernelTypes.ts` carries `surfaceKind`/`externalRefKind`/`externalRefId` and the terminal-status
  set (`succeeded`/`failed`/`cancelled` confirmed at `kernelTypes.ts:80`; `timed_out`/`orphaned`
  not directly grepped but the terminal-status shape otherwise matches).
- **A specific correction to PARALLEL-PLAN.md's own framing:** that plan (written 2026-07-13, one
  day before the kernel even landed) said "`resumeBinding` is modeled but never called." That is
  no longer true: `kernelCore.ts:1159` calls `input.adapter.resumeBinding(...)` for real, and
  `adapterRegistry.ts:79-81` wraps it in the same contract check as `openBinding`. This rewrite
  re-verified that call site directly rather than trusting either the old audit or the plan.
- **Landed:** 2026-07-14, with continued fixes through 2026-07-29 (`refactor(windows): retire
  agent identity compatibility shims`, #10648).
- **Value / notes:** High. No longer a gap — this was the single largest false-negative in the
  old audit given its size and the "no PR" framing.

## Agent control-plane tools + Desktop Coordinator

- **What it is:** The tools an agent (or the app) can call to manage other agents and drive the
  desktop, plus the "desktop awareness snapshot" / intent-routing substrate.
- **Where (Mac):** `agent/src/runtime/control-tools.ts`, `Chat/AgentControlService.swift`,
  `Chat/DesktopCoordinatorService.swift`, `desktop-intent-router.ts`, `desktop-action-queue.ts`,
  `desktop-context-packet.ts`.
- **Where (Windows, current):** `agentKernel/controlTools.ts` (1423 lines) implements **all 18**
  of the same tools the old audit named from Mac, under identical names:
  `list_agent_sessions`, `get_agent_run`, `build_desktop_awareness_snapshot`,
  `list_desktop_action_queue`, `get_desktop_open_loops`, `build_desktop_context_packet`,
  `route_desktop_intent`, `evaluate_desktop_tool_policy`, `create_desktop_dispatch`,
  `resolve_desktop_dispatch`, `cancel_agent_run`, `inspect_agent_artifacts`,
  `update_agent_artifact_lifecycle`, `send_agent_message`, `spawn_background_agent`,
  `spawn_agent`, `run_agent_and_wait`, `set_desktop_attention_override` (confirmed by grepping
  every `case '...':` branch in the tool-call switch, `controlTools.ts:650-1043`). Supporting
  modules: `desktopIntentRouter.ts` (150 lines), `desktopActionQueue.ts`, `desktopContextPacket.ts`
  — all imported and called from `kernelCore.ts` (`routeDesktopIntent` at `kernelCore.ts:635-647`).
- **Wired live, not dead code:** `main/ipc/agentControl.ts` (49 lines) is imported and its
  `registerAgentControlIpc()` called at `main/index.ts:1014`, alongside `registerCodingAgentHandlers`
  and `registerAgentCardHandlers` for the companion IPC surfaces.
- **Landed:** first control-tool commit 2026-07-14 (`feat(windows/agent): control-tool dispatch +
  wire the INV-AGENT leaf-role guard`), continued fixes through 2026-07-29.
- **Value / notes:** High. No longer a gap. This is the item the old audit was most confidently
  wrong about — it called this "Absent... No [PR coverage]" when in fact every tool it named by
  hand from the Mac source already existed under the same name in the Windows tree.

## Desktop tool-policy engine

- **What it is:** A capability-bundle permission engine deciding allow/deny/user-approval for a
  tool call.
- **Where (Mac):** `agent/src/runtime/desktop-tool-policy.ts` (374 lines).
- **Where (Windows, current):** `agentKernel/desktopToolPolicy.ts` (412 lines). Explicitly
  documented in its own header as "one of THREE independent policy axes" alongside
  `executionPolicy.ts` (leaf-worker spawn/message gating) and `codingAgent/toolPolicyStub.ts`
  (per-bash-command ACP permission). 12 `DesktopCoordinatorBundle` values (one more than the old
  audit's Mac count of 11 — plausibly Windows added a bundle, or the old audit's Mac count was off
  by one; not re-verified against Mac source per scope), risk/privacy/approval tiers, deny-by-default,
  and — per its own code comment — resolves control tools *and* the ~31-entry product-tool manifest
  (`omiToolManifest.ts`, 1750 lines) so an unknown tool name fails closed rather than falling
  through to a bundle-only judgment that could be gamed.
- **Landed:** 2026-07-14.
- **Value / notes:** Medium. No longer a gap.

## Floating-bar background-agent delegation + AgentPill

- **What it is:** Spawn background agents from the floating bar, each surfaced as a live pill
  with status, voice/text follow-up, stop, dismiss.
- **Where (Mac):** `FloatingControlBar/AgentPill.swift` (2195 lines), `AgentDelegationExecutor.swift`,
  `AgentDelegationResolver.swift`, `DelegationBriefValidator.swift`.
- **Where (Windows, current):** `components/bar/AgentPillView.tsx` (123 lines),
  `hooks/useAgentPills.ts` (310 lines), `components/bar/agentPills.ts` (pure projection model),
  `components/bar/agentPillTranscript.ts` (per-pill transcript synthesis).
- **How it works:** `useAgentPills.ts`'s own header comment states the intent directly: "Faithful
  port of macOS' AgentPillsManager projection + per-run polling," reading the same canonical
  source the LLM does (`list_agent_sessions` filtered to `surfaceKind: 'floating_bar'`), polling
  each active run's `get_agent_run` on a 2000ms cadence (`LIST_POLL_MS`/`RUN_POLL_MS`,
  matching Mac's 2s poll at `AgentPill.swift:1775` cited by name in-code) — with an idle
  optimization Mac doesn't need to document (Windows drops to a 30s heartbeat when no pills are
  active, leaning on a kernel push event to re-arm instantly). Viewed-finished pills get a TTL
  eviction (`VIEWED_FINISHED_TTL_MS`) and there's a soft-cap trim (`trimForSoftCap`), both fail-open
  on any door-call error so a bad poll can never crash the render.
- **One real gap that persists from the old audit, now more precisely scoped:** Mac's
  `AgentPillsManager.spawnFromUserQuery` parses agent-count ("spawn 3 agents") and provider
  directives ("ask hermes to…") straight out of the bar's free-text input via regex. No Windows
  equivalent of that specific text-parsing step was found (`grep` for `spawnFromUserQuery`-style
  count/provider parsing in `components/bar/**` and `hooks/useAgentPills.ts` returns nothing);
  Windows' bar text still goes through the single-named-agent `detectAgentTask` regex in
  `lib/agentTask.ts`, or relies on the model itself calling `spawn_agent` multiple times from
  chat. The pill *projection and lifecycle* is a faithful, complete port; the *natural-language
  spawn-request parsing* that populates it from bar text is thinner than Mac's.
- **Landed:** 2026-07-19 (`feat(windows/agents): bar floating-agent-pill UI + per-pill transcript
  view (B3)`), with a follow-up fix 2026-07-25.
- **Value / notes:** High. Old audit called this "Absent... most visible, differentiated agent
  UX" with no PR coverage; it shipped a month before that was written.

## Multi-provider agent connect + Claude OAuth (not a Mac-style chat-backend picker)

- **What it is on Mac:** A user-facing switch between chat backends (`BridgeMode`) — Omi AI,
  Claude via OAuth, Hermes, OpenClaw — persisted and hot-swappable, so which backend answers
  *every* chat message is an explicit, sticky setting.
- **Where (Mac):** `Providers/ChatProvider.swift` (`BridgeMode`), `SettingsContentView
  +FloatingBarAndChat.swift`, `Chat/ClaudeAuthSheet.swift`, `agent/src/oauth-flow.ts`.
- **What actually shipped on Windows — a different shape, not a subset:**
  `components/settings/tabs/AgentsTab.tsx` is "Settings → Agents: connect the coding agents Omi
  can delegate tasks to" — PATH auto-detection per external agent (OpenClaw/Hermes/Codex), a
  one-click Connect that fills the known launch command *and* runs a real ACP handshake (so a
  green check means the command actually works, not just that a string was saved), install
  commands one copy away, and a Codex-specific paste-your-OpenAI-key lane (validated, no browser
  needed). Claude Code sign-in is `claudeOAuth.ts` (490 lines): a PKCE loopback flow that writes
  the Claude Agent SDK's own `.credentials.json` format directly — meaning the Windows ACP
  adapter and the real Claude Code CLI (if also installed) share the exact same credentials file,
  which sidesteps the "needs a Windows Credential Manager / DPAPI equivalent" concern the old
  audit raised for Keychain storage; there's simply no separate encrypted store to build for this
  one credential (unlike BYOK provider keys, which do go through `safeStorage`/DPAPI in
  `agentKernel/byokStore.ts`).
- **What's genuinely still missing vs Mac:** there is no persistent "default chat backend"
  toggle. Provider selection on Windows happens per-message: `detectAgentTask` (`lib/agentTask.ts`)
  mention-detects a named/unnamed agent in the text and hands it to `codingAgentRun`, or the model
  itself calls the `spawn_agent` control tool. This is architecturally different from Mac's
  sticky `BridgeMode`, and it's a legitimate open design question for the sequencing plan (not
  addressed here) whether Windows should add a Mac-style persistent picker or keep the
  detection-based UX.
- **Value / notes:** High. Old audit's "Absent — no settings UI/OAuth yet" is wrong; a settings
  UI and OAuth both exist and are more capable per-provider (real handshake test, Codex API-key
  lane) than the old audit's framing anticipated, even though the overall UX model differs from
  Mac's toggle.

## Structured chat content blocks

- **What it is:** Rich in-message rendering beyond plain text.
- **Where (Mac):** `Chat/ChatContentBlockCodec.swift`, `ChatStreamingBuffer.swift`.
- **Where (Windows, current):** The contract is published in `shared/chatContent.ts` — a
  `ChatContentBlock` discriminated union with `text`/`toolCall`/`thinking`/`discoveryCard`/
  `agentSpawn`/`agentCompletion` variants, explicitly documented as mirroring
  `ChatProvider.swift:165-191` including the post-stream pruning rule (drop `thinking`, keep only
  agent-related tool groups). Of these, **`agentSpawn`/`agentCompletion` are actually rendered**:
  `components/chat/AgentThreadCard.tsx` renders them as understated cards (spawn = running spinner
  + objective; completion = status dot + output, three states succeeded/stopped/failed), and
  `ChatMessages.tsx:107-119` filters a message's `blocks` down to exactly these two types before
  falling back to the plain-text bubble path.
- **What's still not rendered:** `toolCall`, `thinking`, and `discoveryCard` blocks have no
  component consuming them anywhere in `components/chat/**` (grepped for `contentBlocks`,
  `thinking`, `toolCall`, `discovery` inside `ChatMessages.tsx` — zero hits beyond the type
  import). `ChartData` similarly has a published type with an explicit "no UI in this PR" comment.
- **Value / notes:** High for agent transparency; genuinely upgraded from "Absent" to "Partial,"
  and the part that *did* ship (agent cards) is exactly the part the old audit separately flagged
  as needed for the AgentPill feature — so this is not an isolated fix, it's the rendering half of
  the AgentPill/kernel work landing together.

## Chat attachments (image / file upload)

- **What it is:** Attaching images/files to a chat message, with previews and upload.
- **Where (Mac):** `Chat/ChatAttachment.swift`.
- **Where (Windows, current):** `lib/chatAttachments.ts` (154 lines, staging/status tracking),
  `lib/chatAttachmentUpload.ts`, `components/chat/ChatAttachmentStrip.tsx` (132 lines). The strip
  renders a vertical column of cards — a 140px image tile with filename overlay (falling back to
  a document card on thumbnail-load failure) or an icon-badge document card — explicitly
  documented as non-interactive in v1 (no open/reveal/copy) because "Windows keeps no local source
  path after upload." Wired into the send path: `useChat.ts:1004-1007` reads
  `getPendingAttachments().filter(uploaded)` and maps to `serverId`s sent as `fileIds`.
- **Value / notes:** Medium. No longer a gap — flips from "Absent" to "Present," with one
  documented UX simplification (no open/reveal) versus Mac.

## Chat resources / generated artifacts

- **What it is:** Agent-produced files appearing as resource cards you can open/reveal.
- **Where (Mac):** `Chat/ChatResource.swift`, `AgentArtifactProjection.swift`.
- **Where (Windows, current):** The `ChatResource` interface is published in `shared/chatContent.ts`
  (origin, state machine `uploading→ready→failed→retained→opened→dismissed`, matching Mac's state
  set), and the backend half is real: `agentKernel/artifactStorage.ts` (313 lines),
  `kernelArtifacts.ts`, `artifactFilters.ts`, and `controlTools.ts`'s `serializeArtifact` function
  are all live and used whenever a spawned agent run produces a file. But `grep -rln "ChatResource"
  src --include=*.tsx` outside the type file itself returns nothing — no component in
  `components/chat/**` renders one.
- **Value / notes:** Medium. Old audit's UI-facing verdict ("Absent") still holds, but for a
  narrower reason: the artifact *machinery* this feature would sit on top of is no longer missing,
  only its chat-surface presentation is. This is a smaller remaining lift than the old audit
  implied (it read as needing the whole artifact pipeline; it only needs a renderer now).

## Chat write-path continuity

- **What it is on Mac:** The invariant that a chat turn is written exactly once and consistently
  across surfaces (main chat, floating bar, voice) via optimistic staging + a single idempotency
  key.
- **Where (Mac):** `Chat/KernelTurnProjection.swift`, `ChatContinuityInvariants.swift`.
- **Where (Windows, current):** `lib/chat/agentThreadCards.ts`'s `mergeAgentCards` function, whose
  own header comment tags it "B4, INV-CHAT-1" — i.e. this is a named, deliberate invariant in the
  Windows codebase now, not merely "N/A, simpler" as the old audit framed it. It merges
  kernel-authoritative agent-spawn/completion cards into the one local renderer thread, matched by
  `chatId`, so a card produced by the bar's floating-agent flow and one produced by main-window
  chat both resolve into a single consistent history without duplicating turns.
- **Value / notes:** Medium. Still correctly scoped as lower-stakes than Mac's version, because
  Windows still has effectively one write surface for ordinary chat turns — but this rewrite
  corrects the old audit's implication that Windows has *no* mechanism here at all. It has a
  narrower one, under its own INV tag, purpose-built for the one place multi-surface writes
  (main chat + bar pills) actually collide today.

## Stall detection

- **What it is:** Detecting a slow/stalled turn or tool call and surfacing a banner.
- **Where (Mac):** `Chat/StallDetector.swift`, `StallThresholds.swift`.
- **Windows status:** **Absent, confirmed unchanged.** No file matching `*stall*` exists anywhere
  under `desktop/windows/src`. The only timing safety net is the same coarse, all-or-nothing 180s
  watchdog that also backs the C5 abort-path fix (`CHAT_STREAM_TIMEOUT_MS`, `useChat.ts:75`) — it
  fires once at 180s with no intermediate "slow…" state, unlike Mac's graduated
  running→slow→stalled ladder.
- **Value / notes:** Medium. Genuinely still a gap, correctly identified by the old audit.

## Screen-context auto-injection into chat

- **What it is:** Auto-attaching on-screen context to a chat turn.
- **Where (Mac):** `Chat/ScreenContextTelemetry.swift` + `ScreenContextWorkContextBuilder`.
- **Windows status:** **Partial, confirmed unchanged since the old audit and since the repo
  split.** `lib/screenContext.ts` (36 lines) has literally zero commits (`git log` returns exactly
  one entry, the 2026-06-11 monorepo-split move) — it always prepends an OCR text snapshot, with
  no eligibility policy, no tool-mediated on-demand capture, no permission-aware skip. This is
  the one item in this file where re-verification found the old audit was simply, correctly,
  right, and nothing has moved.
- **Value / notes:** Medium, unchanged. Flagged in PARALLEL-PLAN as pending an "as image" upgrade
  (Mac sends `imageBase64` in the kernel query); that upgrade has not started.

## Agent runtime error taxonomy + recoverable-error UI

- **What it is:** Structured, sanitized failures with user-friendly messages and recovery
  affordances.
- **Where (Mac):** `agent/src/runtime/failures.ts`, `Chat/AgentRuntimeFailure.swift`,
  `ChatErrorState.swift`.
- **Where (Windows, current):** `codingAgent/failures.ts` (238 lines) is a real port, not a stub.
  Separately, `lib/chat/chatErrorCopy.ts` (60 lines) maps a raw chat-send error string to
  plain-English copy before it ever reaches a bubble — 401/403→"Please sign in to continue,"
  429→framed as the server being busy (explicitly not blaming the user for typing fast), with a
  documented ordering rule (explicit HTTP status wins over an offline heuristic). `shared/
  chatContent.ts` also publishes the five-state `ChatErrorState` union (`authRequired`/`timeout`/
  `bridgeUnavailable`/`interrupted`/`noDataFound`) mirroring Mac's swift type name-for-name.
- **What's still missing:** No dedicated recovery-CTA component (retry button, sign-in button)
  was found consuming that five-state union in `components/chat/**` — the friendly-copy mapping
  softens the *text* of the error but there's no structured recovery UI yet.
- **Value / notes:** Low-Medium, upgraded from the old audit's "Absent (raw `Error:` bubble)" —
  that specific claim is now false; the error text is sanitized. The affordance gap (no CTA) is
  real and unchanged in substance.

## Rich Omi-data + desktop tool-calling loop inside chat

- **What it is:** In-chat, model-driven access to Omi's own data via tools (SQL, memories, tasks,
  screen).
- **Where (Mac):** `Chat/ChatToolExecutor.swift`, `Chat/DesktopCapabilityRegistry.swift`.
- **Windows status:** **Partial, largely unchanged for the specific thing the old audit was
  talking about (default chat's own local enrichment), but the surrounding infrastructure has
  grown substantially.** `lib/localAgent.ts:33` still reads `const ENRICH_ENABLED = false`, with
  the same "Floor-only mode" comment the old audit quoted — that specific flag has not moved, even
  though the file was touched 2026-08-09 for an unrelated managed-structured-lane change. What
  *has* changed is that a full, separate turn-by-turn tool-calling surface now exists for
  spawned coding agents: `agentKernel/controlMcpBridge.ts` and `toolRelayBridge.ts` are the
  model-facing MCP/relay edges (documented in-code as Windows' analog of Mac's
  `omi-tools-stdio`/`startOmiToolsRelay()`) serving both the 18 control tools and the product-tool
  manifest to any spawned ACP or pi-mono agent. So the tool-calling *loop itself* is real and
  live — it's just gated to delegated agent runs, not (yet) wired into the default chat turn the
  way Mac's `ChatToolExecutor` is.
- **Value / notes:** Medium-High. Status label is unchanged from the old audit ("Partial") but
  the reasoning is materially different: it's no longer "the tool loop barely exists," it's "the
  tool loop exists and is real, it's just not the loop that answers your default chat message."

## ChatProvider orchestration + warmup (architecture) — unchanged from old audit

Not re-verified in depth this pass beyond confirming `useChat.ts` (now 1679 lines, up from
whatever length backed the old citation) still has no multi-owner projection or session-prewarming
equivalent to Mac's `ensureBridgeStarted`. Given how much else in this file changed, this item
gets a lower-confidence "still true" than the others — worth a closer pass if Stream 1 work
touches warmup latency.

## pi-mono provider (the "Omi AI" baseline) — status upgraded

- **Old audit:** "Present (equivalent) — Windows chat is functionally the piMono/hosted-Omi
  lane."
- **Current:** Not just equivalent — this is now **literally** the mechanism. `useChat.ts`'s own
  comments (`:645`, `:1080`) call the kernel-routed `pi_mono` adapter "the pi_mono engine (now the
  default)." `codingAgent/piMono.ts` is 1425 lines, larger than Mac's 1041-line `pi-mono.ts`.
  This executes PARALLEL-PLAN's decision gate #7 ("pi-mono default — DECIDED") for real, ahead of
  gate #8's staged rollout plan for making the *kernel* the default chat backend (gate #8 wanted
  this flagged off in the first release and flipped only after specific safeguards — worth
  checking whether those safeguards (fallback telemetry, continuity guard test) actually landed
  before this shipped as default; not verified in this pass).
- **Value / notes:** Confirms Windows already has the "Omi AI" tier, now for real via the kernel
  rather than the older direct-to-backend path the original audit assumed was still primary.

## agent VM (hosted always-on agent VM) — unchanged, out of scope for this pass

No client-side change; still a backend/VM concern (`backend/agent_vm/`), not re-verified.

## Chat Lab (internal dev tool) — unchanged, out of scope for this pass

Still not a shippable feature; not re-verified.

---

## Spotted outside my scope

- The magnitude of this correction (a fully-shipped, ~90-file, 150-commit subsystem the previous
  audit called "does not exist as PRs yet") suggests the 00-INDEX repo-wide grep step for this
  area was run against a stale worktree, or the PR-stack numbers (#9304 etc.) were never
  reconciled against what actually landed on `main` under different branch names
  (`karthik/win-agents-4-polish`, `feat/win-agent-kernel`, …). Worth checking whether other audit
  files (00-13) share the same failure mode before trusting their "Absent" verdicts at face value.
- Windows added a fourth external coding-agent adapter, Codex (`codingAgent/codex.ts`), that the
  old audit's Mac-side citation list did not carry at all. Either Mac has gained Codex support
  since the Mac reference snapshot was taken (making the old audit's Mac list stale in the other
  direction), or Windows built support for a provider Mac doesn't have. Not resolved here —
  flagged per the task's "flag Mac-side citations that look suspicious" instruction.
- `AgentsTab.tsx`'s Codex OpenAI-key lane and per-agent "real ACP handshake" Test button are both
  Windows-only conveniences with no Mac equivalent in the old audit's citation list — potential
  Windows-ahead items worth adding to a "Windows-ahead" ledger rather than treated as parity debt.
- The default-chat-engine flip to `pi_mono` (see table above) intersects a PARALLEL-PLAN decision
  gate with explicit required safeguards (fallback telemetry, continuity guard test, staged
  rollout order). This rewrite did not verify whether those safeguards are actually in place —
  only that the flip itself has happened. That's a gap in *this* audit pass, not a resolved
  question, and should be someone's next check before the sequencing plan treats gate #8 as done.
- `desktopToolPolicy.ts`'s bundle count (12) vs the old audit's cited Mac count (11) was not
  reconciled against current Mac source, per this task's scope (Mac not re-verified from scratch).
  Flagged as a possible stale Mac citation rather than resolved.
