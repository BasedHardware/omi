# Brief Q2 — bounded shaped context and cache handoff

Branch `lane/msg-launch-hardening`, same user-supplied worktree. Q2 corrects Q item 4.
All commits are local. Nothing pushed, published, merged, deployed or read from
production. No provider calls, gcloud, secrets, stash, workflow additions or forbidden
rendering/citation/help edits. Existing `.agent-req-Q.json` remains untouched.

## Commits

- `8ba86e446db3`: shared bounded context, encrypted epoch summaries, volatile tails,
  explicit history boundaries, streaming usage receipts, surface/per-turn accounting,
  indexes, regression tests and docs.
- `588e10104c98`: checkpoint fully summarized source pages for resumable cold bootstrap.
- `eda7e4e4f4da`: initialize context storage on the database executor.
- Final documentation commit: this report and final validation evidence.

## Per-item status

| Q2 item | Status and result | Main files and evidence |
| --- | --- | --- |
| 1. Stable → volatile | **Done.** Shared system/tools prefix, earlier summary, chronological history, then activity/scope/clock/current request inside final user message. App request context no longer leads history. Current channel forwarded/media evidence is retained. | `retrieval/shaped_chat.py`, `messaging/context.py`, `turn_context.py`, `agentic.py`; pure and real-runner app/Telegram/iMessage byte-prefix tests |
| 2. Bounded window | **Done.** Same shared visible-message policy: 10–17 messages, front advances eight. Channel events no longer override shared message history. Original history remains searchable. No hard event-size wall. | `database/chat_context_reads.py`, `chat_history_window.py`, `gateway.py`, `app_awareness.py`; window tests and messaging/mobile compatibility suite |
| 3. Rolling summary | **Done.** Cheap `chat_graph` summary, max 2,400 characters; dropped source pages scoped to owner/session, 40 documents/page and 12,000 characters/model chunk. Summary precedes history and only changes when anchor advances. Encrypted state, mutation generation, CAS revision, active-link/account fences. Fully summarized pages checkpoint; failure cannot skip a partial page. `/new` copies no summary. | `database/chat_context.py`, `chat.py`, `messaging.py`, `messaging/context.py`, `history.py`; epoch/failure/resume tests, six emulator tests, desktop journal/clear regressions |
| 4. Digest | **Done.** Latest twenty cross-session activity rows, at most 3,200 characters, retained encrypted in volatile session state. No permanent digest append. | `history.py`, `messaging/context.py`, `gateway.py`, `app_awareness.py`; final-message-only and cap tests |
| 5. Cache contract | **Done for supported contract.** Existing system breakpoint plus eligible historical endpoints; keeping former history endpoints enables cumulative prefix reads within an epoch. Only resolved GPT-5.6 receives explicit options. TTL config validates `30m`. **Longer TTL unavailable:** current gateway and provider support only 30m. Minimum 1,024 tokens, first-two/latest-fifty breakpoint lookup, at most four writes/call. | `prompt_cache.py`, `messaging/context.py`; SDK/wire/resolved-model/real-runner tests; [official prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching), local `llm_gateway/gateway/validator.py` |
| 6. Usage telemetry | **Done.** Provider input/read/write counts in daily feature/model, surface/model and hashed per-turn/model documents. App and each channel distinguished. Preserve terminal gateway cache-write usage before LangChain drops it. Prometheus counter `omi_chat_agent_tokens_total` with static surface/kind labels. | `usage_tracker.py`, `gateway_client.py`, `database/llm_usage.py`, `messaging/metrics.py`; callback/SDK tests and emulator aggregate/turn assertions |
| 7. Tests | **Done locally.** Byte-identical stable prefixes through actual shared shaped runner and assembly; clock/scope/digest in final turn; epoch boundary summary, bounded window, resume, isolation and mutation/revocation guards. | Manifests `backend/testing/messaging/context-*-files.txt`; commands below. Synthetic providers only; production cache hit rate is unmeasured. |

Summaries are lossy continuity aids. Exact older details remain available through
`search_chat_history`; this is not a claim of lossless model memory. Message count is
bounded, not an absolute token budget: a few unusually large historical messages can
still be expensive. Cold migration may require several turns/timeouts to finish its
resumable bootstrap. Unsupported transports reporting no cache-write field record zero.
No provider pricing or actual hit-rate claim is inferred from local prefix equality.

## Validation

Run from repository root, all backend tests through `backend/test.sh`, credentials unset:

```sh
env -u GOOGLE_APPLICATION_CREDENTIALS BACKEND_UNIT_TEST_FILE_LIST="$PWD/backend/testing/messaging/context-unit-files.txt" bash backend/test.sh
```

**1,239 passed, seven skipped**, one selector-deselected case across 34 files.
Log `/tmp/q2-tests-final-r2.log`. Seven skips are explicit service-dependent cases;
separate anonymous loopback tests below execute the new Firestore contracts.
This full run preceded the final completed-page checkpoint addition; its affected module
was rerun below. Initial failures exposed obsolete digest assumptions, mutation write-count
assertions, missing synthetic model metadata and call-phase import overhead; corrected
without duration exceptions or skip flags.

```sh
env -u GOOGLE_APPLICATION_CREDENTIALS MESSAGING_TEST_FIRESTORE_HOST=127.0.0.1:18885 BACKEND_UNIT_TEST_FILE_LIST="$PWD/backend/testing/messaging/context-emulator-files.txt" bash backend/test.sh
```

**Six passed**. Log `/tmp/q2-emulator-final.log`. Emulator uses anonymous credentials and
random `demo-context-*` projects on loopback; no cloud reads/writes.

```sh
printf '%s\n' tests/unit/test_shaped_chat_context.py > /tmp/q2-checkpoint-files.txt
env -u GOOGLE_APPLICATION_CREDENTIALS BACKEND_UNIT_TEST_FILE_LIST=/tmp/q2-checkpoint-files.txt bash backend/test.sh
```

**21 passed**, including resumable completed-page summary and actual SDK/runner tests.
Final affected-suite log `/tmp/q2-checkpoint-tests-final.log` (after executor initialization fix).

```sh
scripts/pr-preflight --suggest
env -u GOOGLE_APPLICATION_CREDENTIALS OMI_PR_BODY_FILE=/tmp/q2-pr-body.md make preflight
```

**All 44 checks passed** (154.10s), including generated index/query checks, import
purity, source closure, isolation, async blockers and repository ratchets. Log
`/tmp/q2-preflight-metadata.log`. An initial invocation without local PR metadata
stopped because this unpublished lane has no PR; the concrete local draft supplied
`UI-Evidence: none`, failure-class metadata and invariant citation, with no PR created.
A final run pinned to the supplied base checks the completed-page checkpoint commit;
its first attempt caught store initialization on the event loop; moved initialization
to the database executor and reran the affected 21-test suite. Final rerun results
are **all 44 checks passed** (252.56s), log `/tmp/q2-preflight-final-r2.log`, source
`eda7e4e4f4da`. Command:

```sh
env -u GOOGLE_APPLICATION_CREDENTIALS python3 .github/scripts/pr_preflight.py --lane local --base f0d1b5496582 --pr-body-file /tmp/q2-pr-body.md
```

Pinning the user-supplied base skips no checks and avoids attributing subsequently
fetched upstream work to this lane. Advisory large-file warnings remain for existing modules.
Whitespace checks passed. The task-owned loopback emulator was stopped after testing.

## Deploy-time changes

1. Publish the generated `chat_context_summary_source` messages composite index:
   `chat_session_id ASC`, `created_at ASC`, document name ASC; wait for readiness.
2. `OMI_CHAT_PROMPT_CACHE_TTL=30m` or unset. Unsupported TTL rejects configuration;
   no claim of 24h support. Flag registry and generated docs updated.
3. Derived encrypted `shaped_context`, `shaped_context_revision`, user
   `chat_context_generation` are created lazily. No historical migration or additional
   scheduler job. Q's opt-in maintenance chart and other deploy steps still apply.
4. Ensure Prometheus scrapes backend counters and inspect surface token hit ratio
   cache_read/input; inspect per-turn documents for input/read/write attribution.
5. Q's Helm/index/provider rollout remains David's later action. No rollout
   or production validation was attempted. No David decision is needed for local code;
   deployment timing, index readiness and actual cache benefit need release verification.

## 200-turn token estimate

Illustrative turn 200: 399 stored messages before its answer (one user + one assistant
per prior turn), average 250 tokens/message; exclude stable system/tools `S`, tool
results, images and provider overhead. The historical unbounded channel evidence path
would send roughly **99,750 + S** tokens, plus clock/digests. Q-only forty-event pruning
would instead have roughly **10,000 + S**, but still used volatile leading evidence.

Shared policy at 399 visible messages selects **15 messages**, roughly 3,750 tokens.
Add up to ~600 summary, ~800 digest and ~100 request metadata: **5,250 + S** input tokens,
about **94.7% less variable context** than the unbounded path. Worst 17-message epoch
is roughly **5,750 + S** under these same average assumptions. Character caps are
approximate token estimates, not exact tokenizers.

Within a warm epoch, the previous stable history prefix plus summary/system/tools is
eligible for cache reads. Roughly two newly historical messages, current user and
volatile digest/metadata remain fresh (~1,650 tokens in this example); an omitted digest
reduces that. TTL expiry, epoch transitions, tool changes and cache misses require full
input. Cache eligibility is measured locally; actual discount requires production usage.

Each eight-message advance adds ~2,000 dropped tokens plus a ~600-token prior summary
to the cheap summary model, amortized around **650 cheap-model input tokens/turn** for
four two-message turns, excluding bootstrap and chunking. Existing long chats pay a
one-time bounded, resumable bootstrap across dropped history. Summarization input is
additional usage, not free or counted as chat-agent cache savings.

The report itself is `backend/docs/messaging-context-cache-report.md`.

## Files touched in Q2

```text
backend/database/chat.py
backend/database/chat_context.py
backend/database/chat_context_reads.py
backend/database/llm_usage.py
backend/database/messaging.py
backend/database/messaging_queries.py
backend/docs/feature-flag-registry.md
backend/docs/messaging-channels.md
backend/docs/messaging-launch-hardening-report.md
backend/docs/runbooks/messaging-channels.md
backend/testing/messaging/context-emulator-files.txt
backend/testing/messaging/context-unit-files.txt
backend/tests/support/firestore_query_driver_registry.py
backend/tests/unit/test_desktop_migration.py
backend/tests/unit/test_messaging_channels.py
backend/tests/unit/test_messaging_live_qa.py
backend/tests/unit/test_messaging_threads.py
backend/tests/unit/test_shaped_agent.py
backend/tests/unit/test_shaped_chat_context.py
backend/tests/unit/test_shaped_chat_context_firestore.py
backend/utils/llm/gateway_client.py
backend/utils/llm/prompt_cache.py
backend/utils/llm/usage_tracker.py
backend/utils/messaging/ARCHITECTURE.md
backend/utils/messaging/app_awareness.py
backend/utils/messaging/context.py
backend/utils/messaging/gateway.py
backend/utils/messaging/history.py
backend/utils/messaging/metrics.py
backend/utils/messaging/projection.py
backend/utils/messaging/turn_context.py
backend/utils/retrieval/agentic.py
backend/utils/retrieval/shaped_chat.py
config/feature-flags.yaml
firestore.indexes.json
```
