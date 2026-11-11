# Chat continuity write-path contract (INV-6)

The engineering write-path rules for the one shared desktop chat timeline. The
product-level statement is [`product/invariants/chat-continuity.md`](../../../product/invariants/chat-continuity.md)
(INV-CHAT-1); this file holds the Swift-side contract, the PR definition of
done, and the gauntlet gate policy. The component guide keeps the invariant
summary and links here.

## Chat Continuity Write-Path Contract (INV-6)

Invariant: Main Chat, Home chat, and floating/notch chat are one timeline over one
`ChatProvider` (`historyChatProvider`). Kernel `main_chat` turns are the durable
source of truth; journal acceptance publishes the immediate pending projection,
and UI must never append a pre-journal turn.

Rules (fail the PR if any break):
1. **Single provider + floating viewport** — floating presentation is chrome + a
   viewport cursor (`FloatingChatViewport` message ids / `clientTurnId`) over
   `ChatProvider.messages`. It must not own a second durable transcript array
   (`chatHistory` of `ChatMessage` copies is forbidden).
2. **Single `turn_recorded` UI apply gate** — only `KernelTurnProjection` on
   `ChatProvider.mainInstance` (`historyChatProvider`) may attach the runtime
   turn handler (one replaceable slot). Speculative warm and other surfaces must
   reuse `mainInstance`; never construct a second `ChatProvider()` that calls
   `attachClient` / `setTurnRecordedHandler` on the shared runtime.
3. **One idempotency key per logical turn** — call `recordJournalExchange` (or
   the corresponding kernel control RPC) with one opaque continuity key and
   await acceptance before binding a visible row. Direct-control spawn receipts
   already materialize their exchange; refresh that journal instead of issuing a
   second write. Never dedupe by assistant/user text.
4. **Kernel apply is idempotent** — `KernelTurnProjection` upserts only by the
   canonical turn ID published by ordered journal replay. Rejection must leave no
   visible row, and replay/acknowledgement must replace rather than append.
5. **Cross-surface agent identity is structured** — `agentSpawn` / `agentCompletion`
   content blocks (plus tool-block `spawnedAgentID` / sessionId / runId lines) are
   authoritative. Persist structured blocks through the kernel journal/outbox so
   they survive reload; kernel apply still materializes `agentCompletion` from
   bracket text for legacy rows. Legacy `[Background agent id=…]` bracket
   text remains dual-read only. Do not invent new free-text formats; extend the
   schema + tests together.
   Proactive notifications never journal Chat turns. Owner-scoped, TTL-bounded
   context may inform user follow-ups. The shared provider filters historical
   automatic entries by provenance, preserving rich reply blocks.
6. **Pill cache is derived** — open-by-id hydrates from kernel (`listFloatingAgentPills`
   / `listAgentSessions` / `inspectAgentRun`) when the in-memory pill is missing;
   refresh-on-miss is a fast path only. Success = resolvable agent after hydrate.
   Do not keep a second durable pill store.
7. **Snapshots are aliases** — `automationFloatingChatSnapshot` ==
   `automationChatSnapshot` / `automationMainChatSnapshot` over the same messages;
   no surface-specific transcript filter.
8. **Resources live on the producing message** — artifacts attach to the
   `ChatMessage` that produced them (stage/promote keeps `resources` on that id).
   UI must not invent a standalone artifact-only turn. Floating/notch resource
   strips bind `message.displayResources` on viewport-derived messages only
   (never flatMap the whole provider timeline). Aggregate strips must filter
   with `ChatContinuityInvariants.resourcesBelongingToMessages` /
   `FloatingControlBarState.viewportDisplayResources`.
9. **Agent card/list preview = prompt/objective** — collapsed header / list
   subtitle uses `ChatContinuityInvariants.agentPreviewText(prompt:output:)`
   (prompt wins; output is expanded-body only). Do not put raw completion output
   in the one-line preview.
10. **Forbidden dual-write patterns** — never: construct `ChatProvider()` for
    speculative warm (use `ChatProvider.mainInstance`); add
    `addTurnRecordedHandler` / multi-handler append APIs; introduce
    `suppressNextRecordedTurn`; store `@Published var chatHistory` of
    `ChatMessage` copies on `FloatingControlBarState`.
11. **Tests** — continuity behavior changes require a hermetic behavioral test (call
   projection/provider APIs, assert message counts/IDs). Source-string greps for
   function names are not continuity coverage (forbidden-pattern tripwires are the
   exception). Live gauntlet/stress are gates, not substitutes for hermetic tests.

## Continuity PR Definition of Done (INV-6)

A PR that touches chat write-path, kernel projection, floating viewport, agent
timeline identity/open, or pill projection is incomplete until:

1. **Contract still true** — INV-6 rules above hold after the change (or are
   updated in the same PR with a matching behavioral test).
2. **Hermetic behavioral test** for the invariant touched (stage/promote,
   snapshot alias, structured identity, open-by-id hydrate, viewport derive /
   restore, resources-on-message, agent preview text). Not a source grep
   (except forbidden-pattern tripwires).
3. **`./scripts/agent-logic-harness.sh` green** (includes
   `KernelTurnRecordedProjectionTests`, `ChatTimelineContinuityTests`,
   `FloatingControlBarStateTests`, `RuntimeOwnerIdentityTests` in the Swift
   focus filter).
4. **Write-path / cross-surface changes:** run a named-bundle continuity
   gauntlet and note evidence in the PR:
   ```bash
   cd desktop/macos && OMI_APP_NAME=omi-gauntlet OMI_SKIP_TUNNEL=1 ./run.sh
   # run.sh seeds auth after install (UD tokens → app Keychain migrate). Manual reseed:
   # ./scripts/omi-auth-seed.sh com.omi.omi-gauntlet tmp/desktop-auth.json "/Applications/omi-gauntlet.app"
   ./scripts/agent-continuity-gauntlet.sh --suite continuity --bundle-id com.omi.omi-gauntlet
   ./scripts/check-gauntlet-evidence-at-head.sh
   ```
   CI only runs gauntlet `--self-check` (wiring). Live suite is a PR/RC gate,
   not PR CI. Do not assert exact assistant wording.
5. **Hermetic e2e** only if a bridge action/surface contract changed. Do not
   expand flow `covers:` lists as fake continuity coverage.
6. **No second message store** / no new free-text identity format / no
   `suppressNextRecordedTurn`-style dual-write bandage.
7. Changelog fragment only if user-visible.

## Gauntlet / stress gate policy

- **CI:** `agent-continuity-gauntlet.sh --self-check` only (via desktop-core /
  agent-logic harness). Never require live LLM in PR CI.
- **Prompt / gateway changes:** `--suite prompts` on a named `omi-*` bundle;
  P4 requires a completed public-web lookup with a source URL and fails on
  provider tool-choice incompatibilities. **Continuity PRs / RC:** `--suite
  continuity` (typed + PTT + blind recall) after auth seed; `--suite all` for
  RC. Evidence under `.harness/agent-continuity-gauntlet/*/manifest.json` with
  matching git SHA.
- **Anti-flake:** clear owner/kernel surface before probes; per-run nonces;
  hard-fail on blind-recall / structural snapshot only; zero automatic retries
  on model wrongness.
- **Stress:** offline JSONL + forbidden terminal reasons remain the default
  gate; live bridge probes stay optional until continuity `terminal_reason`s
  exist in the taxonomy.

## Live gauntlet vs hermetic INV-6 coverage

Do not confuse these gates — a green live suite does **not** prove write-path
contract rules, and hermetic unit tests do **not** prove bridge/LLM continuity.

| Gate | What it covers | What it does **not** cover |
| --- | --- | --- |
| **Hermetic** (`agent-logic-harness.sh` Swift filter: `KernelTurnRecordedProjectionTests`, `ChatTimelineContinuityTests`, `FloatingControlBarStateTests`, `RuntimeOwnerIdentityTests`) | stage/promote same key → one message pair; floating snapshot aliases main; structured agent identity; open-by-id hydrate preference; floating viewport derive / SoT; resources on producing message; agent preview = prompt; owner-swap preserves Firebase tokens; forbidden dual-write tripwires | Live bridge auth, LLM tool use, PTT hub, race/busy policy under a real runtime |
| **Gauntlet `--self-check`** | Bridge action registration (incl. R3 `ask_main_chat_no_wait` / `main_chat_busy_state`), resilience suite wiring, hermetic contract test presence in harness filter | Any live turn |
| **Live `--suite continuity` / `agents` / `owner` / `prompts`** | Typed + PTT + blind recall, spawn/status, owner swap probe, prompt regressions on a named bundle | stage/promote single-writer, snapshot alias, hydrate preference, viewport SoT (those stay hermetic) |
| **Live `--suite resilience` (R1–R4)** | Cold bridge launch, warm reuse, bridge busy/race rejection (R3; requires real `is_sending`/`is_streaming` once, latch only extends the race window), subagent launch+status (R4) | INV-6 write-path unit invariants above |

`--self-check` fails if R3 race actions or the hermetic INV-6 test methods /
harness filter classes drift away.
