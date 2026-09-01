# Context Cache Efficiency Audit and Implementation

Issue: [#10418](https://github.com/BasedHardware/omi/issues/10418)

## Outcome

This change adds two complementary cache-safe history strategies:

1. Desktop Pi bindings receive the full canonical retained history once, then receive only turns that are new or whose canonical representation changed. A new/replaced binding always receives a full snapshot.
2. Backend agentic chat uses Anthropic's automatic moving message breakpoint and a bounded append-only history epoch. History grows from 10 through 17 visible messages, then resets to the newest 10.

Neither path summarizes, mutates, or drops content that was previously available. There is no cache pre-warming request.

## Cache audit

### Desktop kernel

The context plan is assembled in `desktop/macos/agent/src/runtime/context-snapshot.ts`.

- `RECENT_TURN_LIMIT` is 64.
- Turns are selected newest-first from `conversation_turns`, then reversed into chronological order.
- `olderHistoryStrategy` is `none` until the retained limit is exceeded, then `truncated`.
- `stableCacheIdentity` hashes semantic guidance and the capability version. It does **not** hash profile, memories, tasks, or goals.
- `dynamicContextIdentity` hashes the conversation identity, retained turn IDs, and omitted count.
- `renderContextSnapshot` serializes recent turns, semantic source outcomes, run state, capabilities, and the context plan into one stable JSON payload.

Before this change, `kernel-core.ts` prepended that entire rendered payload to every user turn. In the Anthropic translation:

- one explicit 1-hour breakpoint followed the stable system policy;
- one explicit 1-hour breakpoint was placed on the latest user/tool-result message;
- no independently reusable breakpoint existed inside the serialized 64-turn JSON.

The latest-message breakpoint already cached the growing Pi conversation and agentic tool loops. It could not independently cache repeated old turns embedded later inside each new snapshot because Anthropic cache hashes are cumulative over `tools → system → messages`.

### Backend agentic chat

Before this change:

- `backend/routers/chat.py` always loaded the newest 10 stored messages;
- the window moved at the front every turn;
- `_run_anthropic_agent_stream` marked only the system block;
- tool-loop history and the cross-turn message history had no message breakpoint.

The gateway already persisted `cache_read_input_tokens` and `cache_creation_input_tokens` for every Anthropic attempt. This change extends cache-attempt and TTL classification to Anthropic's top-level automatic `cache_control` shape as well as explicit block markers.

### Stable-prefix staleness

No per-turn stable-prefix invalidation defect was found.

- The desktop stable identity intentionally covers only semantic guidance and capabilities.
- Profile, memory, goal, task, screen, and surface payloads live in the dynamic snapshot.
- Semantic source projection omits transport-only revision/capture metadata, so an identical payload poll does not change the renderer fingerprint merely because it was re-fetched.

Candidate C therefore does not justify a staleness patch in this pass.

## Baseline

### Production backend sample from issue #10418

The issue's telemetry sample covered 749 Anthropic attempts:

- 526 cache reads and 223 explicit 1-hour misses/writes;
- median cached input: about 25.3K tokens;
- median uncached input: about 1.2K tokens;
- p90 uncached input: about 27.5K tokens;
- p95 uncached input: about 331K tokens;
- 62 attempts exceeded 300K uncached tokens;
- the top 10% of attempts represented about 94% of uncached input and 61% of estimated cost.

### Local 64-turn desktop sample

A long local desktop session supplied an exact retained-window baseline:

- 64 retained turns, 6 omitted;
- rendered context: 68,757 characters;
- provider input: 20,403 uncached tokens plus 29,983 cache-read tokens;
- effective cache-read share: 59.5%;
- total provider input footprint: about 50.4K tokens.

Across eight non-tool local turns with positive token telemetry, the aggregate cache-read share was 53.1% and the median per-turn share was 59.5%. Restarting the Pi binding reset the cache read from roughly 30K to 8.8K, confirming that the existing hit was the growing provider conversation prefix, not reuse within the newly serialized context snapshot.

The 64-turn fixture's `recentTurns` payload was 47,166 characters. The oldest 56 turns accounted for 45,051 characters; the latest eight accounted for 2,116.

## Design decisions

### Desktop: binding-scoped delta hydration

`renderContextSnapshotForBinding` records a privacy-local hash per delivered canonical turn.

- First delivery or conversation mismatch: send the complete retained snapshot.
- Same live Pi binding: send only turns with a new ID or changed canonical hash.
- Binding replacement, eviction, or daemon restart: discard the cursor and send a complete snapshot.
- Dynamic sources, run state, capabilities, and the full context-plan metadata continue to be sent every turn.

The cursor is in-memory and keyed by Omi's binding ID. It is committed only after the adapter returns, so a pre-dispatch failure cannot falsely claim hydration. A changed turn is additive in the next delta; existing provider conversation content is never rewritten.

This is the workable form of Candidate A for the actual architecture. Placing a marker “N turns back” inside each repeated JSON string would not create an independent cache segment, and after front truncation its cumulative prefix would miss every mature turn.

### Backend: automatic breakpoint plus bounded append-only epochs

Anthropic automatic caching moves a single breakpoint to the last cacheable block as a conversation grows. The explicit 1-hour system breakpoint remains.

The history selector uses:

- base continuity window: 10 visible messages;
- append epoch: 8 messages;
- maximum transmitted history: 17 visible messages;
- reset: newest 10 at each eight-message boundary.

For totals 10 through 18, selected lengths are `10, 11, …, 17, 10`. Reported messages are excluded from the visible count and over-fetched so they cannot reduce the selected continuity window. Reads are scoped to the active chat session when one exists, otherwise to the active app.

This bounds history, preserves at least the previous 10-message behavior, and gives several append-only turns between deliberate cache resets.

## Candidate assessment

| Candidate | Decision | Savings/impact | Complexity and risk |
|---|---|---|---|
| A: mid-history checkpoint | Implemented as desktop delta hydration and backend automatic moving breakpoint | Highest steady-state savings | A literal marker inside repeated JSON would not work; delivery shape had to change |
| B: compaction summary | Defer | Improves continuity beyond the 64-turn boundary | Requires a canonical additive summary lifecycle and quality evaluation |
| C: stable-prefix scope | No code change | No free hit-rate gain found | Current identity is stable for its actual scope |
| D: tighter filtering | Do not blanket-filter | Possible small token reduction | Failed/streaming turns can carry continuity or retry evidence; dropping them is correctness-sensitive |
| E: adaptive sizing | Backend uses cache-aware bounded epochs; desktop remains 64-turn on first hydration | More predictable cache behavior without reducing continuity | Token-aware compaction can follow after canonical summarization exists |

## Estimated savings

### Desktop

Using the measured 64-turn sample, removing the repeated oldest-56 payload from steady-state turns saves about 13.4K uncached tokens per turn. Estimated uncached input falls from about 20.4K to about 7.0K, a 66% reduction. If the cached prefix remains near 30K tokens, the cache-read share rises from about 59.5% to roughly 81%.

At Claude Sonnet 4.6 rates used by the desktop cost model, converting that repeated slice from regular input to an already-present cached conversation prefix is worth about $0.036 per mature turn before cache-write amortization.

### Backend

For the stable base portion of a four-user-turn history epoch, the 1-hour cache cost multiplier is approximately `2.0 + 0.1 + 0.1 + 0.1 = 2.3` instead of four regular-input passes. That is a 42.5% reduction on the reusable history slice, while newly appended messages remain ordinary incremental input. Tool loops gain the same moving breakpoint without waiting for another user turn.

Actual savings should be compared after deployment using the existing gateway attempt traces:

- cache-read share: `cache_read_input_tokens / total_input_tokens`;
- cache-write share and reset cadence;
- p50/p75/p90/p95 uncached input;
- attempts over 300K uncached tokens;
- first-token latency split by cache hit/miss.

## Implementation ticket pack

### TICKET-01 — Desktop binding delta hydration

Status: implemented.

Acceptance:

- full 64-turn retained history on a new binding;
- only new/changed turns on the next live Pi turn;
- changed canonical turns are re-delivered;
- new/replaced bindings fail safe to a full snapshot;
- source payloads and context-plan metadata remain present;
- behavioral kernel and renderer tests pass.

### TICKET-02 — Backend history and tool-loop caching

Status: implemented.

Acceptance:

- history is chronological after the existing reversal and is scoped by session/app;
- selected visible history is 0–17 messages and never below the previous 10-message window once available;
- a deterministic reset occurs every eight stored visible messages;
- automatic 1-hour caching is present on every agent-loop request;
- explicit stable-system caching remains;
- gateway passthrough and cache accounting recognize both breakpoint forms;
- behavioral database, agent-loop, and gateway tests pass.

### TICKET-03 — Post-deploy measurement

Status: operational verification.

Compare a seven-day post-deploy cohort with issue #10418's baseline. The issue can be closed by this PR because all required fields already exist in gateway attempt telemetry; no new user-visible or production state is required. If p95 uncached input remains dominated by large tool outputs, open a separate problem issue for bounded tool-result projection rather than silently truncating results in this change.

## References

- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic tool use with prompt caching](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching)
