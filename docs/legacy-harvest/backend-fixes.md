# Legacy backend-fix harvest

Analysis only. No code ports in this wave.

Sweep tip used: `origin/main` `3f5bbcdbc00a48b97e6bc78ffa31a187bd9a5e0e`
(2026-08-15 02:36, `feat(desktop): user-facing copy-share-link for conversations (#11612)`).
The shared checkout is a **bare** repository. Its `HEAD` at start and end was
`519cf00ba8c664668e74f4e74ab5c9a0060e6c20`. This lane did not `fetch`.

Existing fate ledger (`docs/legacy-ledger.md`) was read first. Nothing below
reopens `delete-after-cohort` / `keep-under-legacy-prefix` rows; action-items
compat and MCP `mcp1` cursors stay under those fates.

## Table of contents

| Id | Title | Verdict | Severity |
| --- | --- | --- | --- |
| HF-CHAT-001 | Timeout / bounded-stop discards a streamed chat answer from history | PRESENT | high |
| HF-AI-001 | Default task page buries active items behind completed ones | PRESENT | high |
| HF-CHAT-002 | Oversized chat prompt is admitted with no user-visible "too long" reply | ABSENT | high |
| HF-AI-002 | One malformed action-item row 500s the whole list | PRESENT | high |
| HF-MCP-001 | Denied MCP memory read rendered as empty success | NOT-APPLICABLE | high |
| HF-MEM-002 | Malformed cursor rejected before secret / read work | PRESENT | medium |
| HF-AI-003 | Tz-naive action-item dates silently drop extracted tasks | NOT-APPLICABLE | medium |
| HF-CONV-001 | Inverted conversation date range returned as empty success | NOT-APPLICABLE | medium |
| HF-SEG-001 | `start=0` treated as missing, reversing transcript order | NOT-APPLICABLE | medium |
| HF-DATE-001 | Hardcoded `year > 2025` date bound inverts after 2025 | NOT-APPLICABLE | medium |

Verdicts: `PRESENT` = we have the user-visible bug (or the equivalent hole).
`ABSENT` = legacy fixed it; we do not have the fix. `NOT-APPLICABLE` = the
rewrite made the failure mode structurally impossible, or the surface does not
exist. Every `PRESENT` and `ABSENT` row below quotes something this lane ran.

---

## HF-CHAT-001 — Timeout discards a streamed chat answer

Severity: high. Confidence: high.

### 1. Legacy evidence

`610e5c7842` 2026-07-23 `fix(backend): stop discarding chat answers that streamed before a bounded stop (#10305)`

The user watched a complete answer stream in, then saw it replaced by "The
response took too long", and found nothing in chat history, while
`full_response` still held the text. The live helper:

```text
backend/utils/retrieval/agentic.py:1399
    def keep_streamed_answer() -> bool:
        """Preserve what already reached the user when the stream stops early.
        ...
        streamed = ''.join(full_response)
        if not streamed:
            return False
        callback_data['answer'] = streamed
```

Called from the idle-timeout path (`agentic.py:1478`) so a bounded stop emits
the sentinel and persists what already streamed.

### 2. What the bug actually was

A deadline that fires after tokens have already been yielded must keep those
tokens in the durable answer. Replacing them with an empty failed terminal
makes the user believe the model said nothing.

### 3. Whether OUR code has it — PRESENT

`apps/service/chat/generation-supervisor.ts` keeps `state.text` on cancel, and
throws it away on timeout:

```1002:1007:apps/service/chat/generation-supervisor.ts
          void finalize(
            state,
            "failed",
            "",
            { code: "generation_timeout", retryable: true },
          );
```

The max-duration timer at lines 582–584 does the same empty-string finalize.
`finalize` then stores no assistant message when `text.length === 0`
(line 676). History is the store, not the SSE delta log.

Scratch (not committed), scripted source emits `"KEEP ME"` at 2ms then hangs;
liveness `maxRunDurationMs: 10`:

```text
{"terminal":"failed","trace":[{"atMs":0,"kind":"snapshot","text":""},{"atMs":2,"kind":"delta","text":"KEEP ME"},{"atMs":10,"kind":"failed","errorCode":"generation_timeout"}]}
{"eventKinds":["accepted","snapshot","delta","failed"],"deltaTexts":["KEEP ME"],"failedHasMessage":false,"historySenders":["human"],"historyTexts":["keep this"]}
```

User-observed layer: the stream showed `KEEP ME`; `GET` history after the
terminal contains only the human prompt.

### 4. Port proposal, and what makes it safe

Take the **behavior**: on timeout/provider-crash, if `state.text` is non-empty,
persist that assistant message (and still mark the generation `failed` /
`generation_timeout` so the client can show a warning). Leave the Python
`callback_data` / `yield None` machinery, citation index rewriting, and the
canned `AGENT_STREAM_TIMEOUT_MESSAGE` fallback.

Do not port "always succeed a timeout as `done`". A timeout with no tokens
must remain a failed terminal (we already do that). Proof belongs on history
and the SSE terminal, not only on `state.text`.

---

## HF-AI-001 — Default task page buries active items

Severity: high. Confidence: high.

### 1. Legacy evidence

`1cbcc3444d` 2026-07-16 `fix(backend): surface active tasks first so the Tasks page isn't buried under completed items (#9864)`

Prod: 226 active + ~340 completed. Default `GET /v1/action-items` `limit=100`
returned 100 completed; the app auto-flipped to "all done" / "No Tasks Yet".
Predecessor `c475471951` (2026-06-30) paginates **after** the product sort,
which made due-date-first completed rows fill page 1.

Live sort key:

```text
backend/database/action_items.py:448
def _action_item_list_sort_key(item: Dict[str, Any]) -> tuple:
    """Active-first product order (see get_action_items)."""
    return (
        bool(item.get('completed')),
        item.get('due_at') is None,
        ...
```

Default lists then read the incomplete bucket first (`action_items.py:563`).

### 2. What the bug actually was

An unfiltered first page that is admission-order or due-date-order will, for
any heavy user, be all completed tasks. Client-side "hide done" then shows an
empty list.

### 3. Whether OUR code has it — PRESENT

Compat list slices store order with no completed key:

```469:477:apps/service/routes/action-items-compat.ts
  app.get(ACTION_ITEMS_COMPAT_PATH, guarded((context, principal) => {
    ...
    const fetched = deps.store.listRecords(principal.uid).slice(page.offset, page.offset + page.limit + 1);
    return jsonResponse({
      action_items: fetched.slice(0, page.limit).map(projectRecord),
```

`TasksStore.listRecords` sorts by `first_seen_seq` only
(`apps/service/stores/tasks-store.ts:207–210`). `/v1/tasks` uses the same
admission order as its cursor key.

Scratch: three completed rows admitted first, one active last, `limit=3`:

```text
{"status":200,"ids":["done-0","done-1","done-2"],"completed":[true,true,true],"has_more":true}
tasks-read {"status":200,"completed":[true,true,true],"itemCount":3}
```

Both doors hid the open task behind page 1. `get_action_items` chat tool reads
`GET /v1/tasks?limit=25` (`apps/service/chat/action-items-tool.ts:141`), so the
model sees the same burial.

### 4. Port proposal, and what makes it safe

Take **active-first as the default page order** (incomplete before complete;
stable tie-break can stay `first_seen_seq` / `record_id`). Leave Firestore
bucket scans, `_ACTION_ITEMS_LIST_HARD_MAX`, and `datetime.max` due-date
sentinels.

Do **not** add a `completed=` query parameter to `/v1/tasks` (that would move
the ratified wire). Compat `/v1/action-items` already has no such filter; only
its slice order changes. Cursor keyset for `/v1/tasks` today is
`first_seen_seq` — changing default order without changing the cursor binding
would make pages overlap. The safe equivalent is: include `completed` in the
tasks visible keyset **or** keep the cursor on `first_seen_seq` and *filter*
active-first by reading incomplete rows before completing the page, the way
legacy reads two buckets. The next lane should pick one and add a test that
reproduces the three-completed-plus-one-active `limit=3` case above.

---

## HF-CHAT-002 — Oversized chat prompt has no user-visible reply

Severity: high. Confidence: high.

### 1. Legacy evidence

`90cef82cd2` 2026-07-28 `fix(backend): return a clear reply for oversized chat input (#10435)`

A long message / history made Anthropic raise input-too-long. The agent loop
swallowed it; `callback_data['answer']` stayed empty; mobile never got a
`done:` frame. The fix preflights a token budget, trims oldest turns, and when
the **newest** turn alone cannot fit, persists a clear "That message is too
long…" reply through the normal stream contract.

### 2. What the bug actually was

Admitting a prompt the model cannot consume, then failing without a finalized
user-visible sentence, looks like "chat did nothing."

### 3. Whether OUR code has it — ABSENT

`parseCreate` in `apps/service/routes/chat-messages.ts:232–266` accepts any
string `text` (no max). Context packing (`generation-context.ts`) budgets
retrieved items and transcript **tail**, not the current prompt, and never
synthesizes a "too long" assistant message.

Scratch: 250_000-character prompt:

```text
{"status":201,"bodyHead":"{\"message\":{\"id\":\"msg-huge\",\"text\":\"word word word ...","promptChars":250000}
```

The human message is stored. There is no preflight reply. Gateway/provider
failure later is a different terminal, not the legacy user-visible sentence.

### 4. Port proposal, and what makes it safe

Take the **behavior**: if the newest turn alone cannot fit the model window,
persist a short assistant reply that says so and do not call the provider.
Trim older transcript turns (we already cap tail length) before that.

Leave tiktoken, the hardcoded 120k Claude window, and env `MAX_CHAT_INPUT_TOKENS`.
Derive the budget from the configured gateway window with headroom for tools
and the system packet. Do not truncate text on the server while embedding the
full text (do-not-port list). Proof: POST a too-long message, then history
shows the human prompt **and** the "too long" assistant text, and the
generation is terminal without a provider call.

---

## HF-AI-002 — One malformed row 500s the whole action-item list

Severity: high. Confidence: high.

### 1. Legacy evidence

`33f4e9eb0f` 2026-07-03 `fix(backend): skip malformed action items instead of 500ing the whole list (#8867)`

`ActionItemResponse(**item)` on the list/search/pending-sync paths: one
legacy/partial row raised `ValidationError` and hid every action item.

```text
backend/routers/action_items.py
def _safe_action_item_responses(items, *, uid: str = '', context: str = ''):
    """...skipping any that fail validation so one malformed or legacy item
    cannot 500 a whole list endpoint."""
```

### 2. What the bug actually was

A list endpoint that maps every row through a strict projector, and turns the
first throw into 500, makes one bad record indistinguishable from "the
service is down" and hides the good rows.

### 3. Whether OUR code has it — PRESENT (compat and `/v1/tasks`)

Compat `projectRecord` throws `InvalidStoredActionItemError`; `guarded`
returns 500 (`action-items-compat.ts:333–353`, `:427–435`, `:473–477`).

`/v1/tasks` **intentionally** fails the whole page
(`apps/service/composition/tasks-read.ts:63–74`): skip was rejected because a
short page looks complete. That is a documented divergence from legacy skip,
not an accident. It still 500s today.

Scratch:

```text
GET /v1/action-items  (one good row + completed: "not-a-boolean")
{"status":500,"body":"{\"error\":\"internal_server_error\"}"}

GET /v1/tasks?limit=25  (same seed)
{"status":500,"body":"{\"error\":\"internal_server_error\"}"}
```

### 4. Port proposal, and what makes it safe

**Compat `/v1/action-items`:** take skip-and-continue (legacy). That family is
feature-frozen and already swallows into a fixed 500; skipping restores the
shipped Tasks adapter instead of hiding every task. Leave the Pydantic helper
shape; a one-line `try` around `projectRecord` plus a test is enough.

**`/v1/tasks`:** do **not** port skip. The completeness envelope forbids a
short page that looks complete. Fail-closed stays. Optional hardening (not
legacy's skip): a typed 503 / `internal_server_error` is already what we
emit; do not fabricate `completed: false` (the composition already forbids
that, and it is the data-loss path named in the do-not-port spirit).

---

## HF-MCP-001 — Denied MCP memory read rendered as empty success

Severity: high. Confidence: high.

### 1. Legacy evidence

`79d1816b66` 2026-07-28 `fix(backend): report denied MCP memory reads instead of an empty success (#10743)`

Authorization denial returned an empty result with success. The client read
"you have no memories." Four call sites (REST + SSE, search + get) now raise
403 / ToolExecutionError `-32009`. `SHADOW_ONLY` still returns empty on
purpose.

```text
backend/utils/mcp_memories.py:113
def mcp_denied_read_payload(...):
    """Client-visible payload for a refused MCP memory read, or None to serve
    an empty result. ... an empty success is indistinguishable from "you have
    no memories""""
```

### 2. What the bug actually was

A refused read must not share the success-empty envelope of a genuinely empty
account.

### 3. Whether OUR code has it — NOT-APPLICABLE

The rewrite MCP door is a single tool (`read_synthesized_memory`). A denied
grant never calls `readPage`. Scratch:

```text
{"status":200,"body":{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"Tool unavailable"}},"readPageCalls":0}
```

`apps/mcp/protocol.ts:281–282` returns RPC error `-32602` `"Tool unavailable"`
when `visibilityGate` is denied. Hidden-vs-absent for **authorized** reads
(filtered rows) is a different, already-ruled property and must stay.

The dark `query_memory` tool (`apps/mcp/memory-query-tool.ts:76`) returns
`{ kind: "denied" }`, not a completed empty kernel response. It is not
registered on the live handler.

### 4. Port proposal, and what makes it safe

Do not port the four-site classifier or the SHADOW_ONLY empty exception.
Keep returning an RPC error on grant denial. If a later lane adds
`search_memories` / `get_memories` aliases, they must fail the same way — an
empty `content: []` success is the bug.

---

## HF-MEM-002 — Malformed cursor rejected before secret lookup

Severity: medium. Confidence: high.

### 1. Legacy evidence

`11a6cf1733` 2026-08-12 `fix(memory): reject malformed cursors before secret lookup`

```text
backend/utils/memory/memory_service.py:1650
        if cursor:
            cursor_parts = cursor.split('.')
            if len(cursor_parts) != 3 or cursor_parts[0] != 'uml':
                raise HTTPException(status_code=400, detail="invalid_or_stale_cursor:malformed_cursor")
        try:
            secret = cursor_secret()
```

Without the pre-check, junk cursors still performed secret lookup / 503'd as
"Memory cursor unavailable", mixing client error with server misconfig.
Follow-on `008ef016f1` (2026-08-14) then fell back to offset `read()` when the
canonical keyset scan 503'd `"Canonical memory unavailable"` so the **first
page** still served.

### 2. What the bug actually was

Syntactic cursor garbage must 400 before any secret or storage work. A
missing cursor secret must not be the same public outcome as a bad token.

### 3. Whether OUR code has it — PRESENT (the pre-check; not the 503 fallback)

MCP parse rejects an oversized cursor before `readPage`. Scratch:

```text
{"status":400,"body":{"jsonrpc":"2.0","id":2,"error":{"code":-32602,"message":"Invalid params"}},"syntaxReadPageCalls":0}
```

`apps/mcp/protocol.test.ts` T5 (69 related tests green this wave) asserts the
same for `""`, whitespace, 4097 bytes, and a non-string. REST
`readMemoryPage` (`apps/service/composition/memory-read.ts:644–646`) runs
`isSyntacticallyRedeemableCursor` before the core, specifically so a 4096 vs
4097 byte mutation cannot split 400/500.

The **503 → offset first-page fallback** is NOT-APPLICABLE: we have one HMAC
keyset cursor (`mcp1` / chat `chat1`), no dual offset `read()`. A missing
signing secret fails closed rather than serving an unauthenticated offset
scan. Do not port the fallback; it is Firestore-scan debt.

### 4. Port proposal, and what makes it safe

No port. Keep the syntactic pre-check. Do not add a silent offset list when
HMAC keys are missing.

---

## HF-AI-003 — Tz-naive action-item dates silently drop tasks

Severity: medium. Confidence: high.

### 1. Legacy evidence

`3ea609c36b` 2026-08-10 `fix(backend): coerce tz-naive action-item dates to UTC (#11137) (#11138)`

Firestore rejects naive datetimes; extraction/`datetime` (not
`AwareDatetime`) arrived naive or date-only; batch create on the postprocess
path dropped the whole task. Related `99f6dd61b9` converted local due dates
to UTC.

```text
backend/database/action_items.py:186
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            ... pop the field, continue
```

### 2. What the bug actually was

A write path that stores timezone-aware datetimes must not throw away a task
because the extractor omitted `tzinfo`. Overflow on UTC conversion must not
fail the batch.

### 3. Whether OUR code has it — NOT-APPLICABLE

We store `dueAt` as epoch milliseconds. HTTP create requires an explicit
offset (`parseIsoEpochMilliseconds` in `action-items-compat.ts:189–244`).
Scratch:

```text
{"naive":{"status":400,"body":"{\"error\":\"bad_request\"}"},"aware":{"status":200,"due_at":"2026-08-11T12:00:00.000Z"}}
```

There is no Firestore datetime write and no extraction postprocess that
persists naive `datetime` objects. Rejecting naive ISO is stricter than
legacy's coerce-to-UTC, and it does not silently drop a *created* task — the
create never happens.

### 4. Port proposal, and what makes it safe

Do not port coerce-to-UTC on the HTTP door (it would accept `"2026-08-11T12:00:00"`
as UTC and surprise any client that meant local). If a later extraction
worker emits due dates, attach timezone at the worker (account timezone or
UTC, declared) and store epoch ms. Leave Firestore `replace(tzinfo=...)`.

---

## HF-CONV-001 — Inverted conversation date range returned as empty

Severity: medium. Confidence: high.

### 1. Legacy evidence

`7e3476eae3` 2026-06-29 `fix(backend): reject inverted date ranges in the conversations list and count endpoints with 400 (#8580)`
(action-items twin `f2e4830c81` the same day)

Firestore `created_at >= start AND created_at <= end` with `start > end`
returned `[]` / count 0. Callers could not tell a bad request from a genuine
empty window. Mixed naive/aware bounds 500'd (`TypeError`).

### 2. What the bug actually was

Contradictory range filters must 400, not succeed-empty.

### 3. Whether OUR code has it — NOT-APPLICABLE

`GET /v1/conversations` accepts only `limit` / `offset`
(`apps/service/routes/conversations.ts:108–112`). `start_date` / `end_date`
are ignored. Scratch:

```text
{"invertedStatus":200,"plainStatus":200,"sameBytes":true,"invertedLen":430,"sampleKeys":["id","structured",...]}
```

The empty-vs-malformed confusion cannot happen because the filter is not
applied. (Invalid `limit`/`offset` still silently fall back — already pinned
in `conversations.test.ts` — which is a different, older compatibility
choice, not this fix.)

### 4. Port proposal, and what makes it safe

If a later lane adds date filters, reject inverted ranges with 400 **before**
storage, and normalize timezone awareness first. Do not add the filters in
order to port the fix.

---

## HF-SEG-001 — `start=0` treated as missing (load-bearing older-than-90-days class, still live in legacy)

Severity: medium. Confidence: high.

### 1. Legacy evidence

`1205627ba9` 2026-07-27 `fix(backend): keep start=0 segments in order for mentor notifications (#10154)`

```text
backend/utils/mentor_notifications.py:118
            # `start` is an offset into the recording, so the first segment of every
            # conversation is 0.0 — falsy but perfectly valid. `or current_time` replaced
            # it with wall-clock time, which sorted the opening line last
            start_offset = segment.get('start')
            timestamp = current_time if start_offset is None else start_offset
```

This is the textbook "not the obvious way" comment: `x or default` is wrong
when `0` is a legal offset.

### 2. What the bug actually was

The first utterance of every recording has `start=0`. Falsy fallback stamps
it with wall-clock seconds (~1.7e9), so it sorts last into the model.

### 3. Whether OUR code has it — NOT-APPLICABLE

No `mentor_notifications` surface. Listen ingest already orders by `start`,
not arrival (`frontend/packages/testkit/src/test/listen-capture-port.test.ts`
"out-of-order segment arrival paints by content order"). Grep of
`apps/service` found no `start ||` / `get('start') or` fallback.

### 4. Port proposal, and what makes it safe

Do not port mentor. Keep the lesson: any new transcript sort key must use
`== null` / `=== undefined`, never truthiness. No `or current_time`.

---

## HF-DATE-001 — Hardcoded calendar-year date bound

Severity: medium. Confidence: high.

### 1. Legacy evidence

`c09edfce39` 2026-07-29 `fix(backend): bound extracted conversation dates relative to the content date (#10864)`

`if date.year > 2025: continue` plus prompts "Do not include dates greater
than 2025". After 2025 that discarded every real date on the message/text
path and accepted far-future hallucinations on the transcript path. Replaced
with `normalize_extracted_dates` relative to content date (731-day lookahead).

### 2. What the bug actually was

A plausibility bound written as a literal calendar year inverts once that
year passes.

### 3. Whether OUR code has it — NOT-APPLICABLE

Grep of this tree found no `year > 2025` / `greater than 2025`. Formation
validates `account_timezone` with `Intl.DateTimeFormat` even when there is no
temporal claim (`formation-work-producer.ts:223–224`). No extraction prompt
in `apps/service` carries a calendar-year cap.

### 4. Port proposal, and what makes it safe

Do not port the 2025 literal. If formation/extraction grows a date filter,
bound it relative to `observed_at` / content date, never a year constant.

---

## Ranked port queue

The coordinator schedules from this table. Sizes: small = one file + test;
medium = a few files, no wire change; large = new surface or cursor grammar.

| Rank | Id | What the next wave does | Size | Surfaces |
| --- | --- | --- | --- | --- |
| 1 | HF-CHAT-001 | Persist `state.text` on timeout/provider-crash when non-empty; keep `generation_timeout` as the terminal; assert history + SSE | medium | `apps/service/chat/generation-supervisor.ts`, `apps/service/routes/chat-messages.ts`, `generation-scenario.test.ts` |
| 2 | HF-AI-001 | Active-first default page on compat list and `/v1/tasks` without adding a `completed=` query. Resolve cursor keyset vs bucket-read so pages do not overlap | medium | `action-items-compat.ts`, `composition/tasks-read.ts`, `chat/action-items-tool.ts` |
| 3 | HF-CHAT-002 | Preflight newest-turn budget from the gateway window; persist a short "too long" assistant reply; do not call the provider | small | `chat-messages.ts` parse + supervisor / context packet |
| 4 | HF-AI-002 | Skip-malformed **only** on `/v1/action-items` compat. Leave `/v1/tasks` fail-closed | small | `action-items-compat.ts` + test |
| 5 | HF-SEG-001 / HF-DATE-001 | No code. Add a one-line comment on any new transcript timestamp or extracted-date bound if those files are touched | n/a | listen / formation (if touched) |

Do not schedule: HF-MCP-001, HF-MEM-002 fallback, HF-AI-003 coerce-to-UTC,
HF-CONV-001 date filters, Firestore cascade walkers, offset-list 503
fallback, `execute_sql`, clone-draft endpoints, developer webhooks, 20-file
sync-batch isolation, weekly `get_scores` 7-vs-8, pydantic
`ProductMemorySearchItem`, RAG executor reorder (we already sort candidates
before join: `generation-context.ts:236–239`, test
"deterministically compacts priority/conflicting evidence").

---

## Looked at, not opened as findings

These were read far enough to classify. They are not in the TOC because a
port would drag the shape the rewrite exists to escape, or the surface is
absent.

| Legacy | Why it is not a finding |
| --- | --- |
| `a086e119f1` clone drafting wrote to the owner's chat | No clone-draft / stateless-reply router. Chat admission is owner-scoped. |
| `80b9c4e3e4` cascade every Firestore subcollection on conversation delete | No subcollections. `deleteRecord` removes one conversation document. Recursive `collections()` walker is Firestore debt. |
| `54ef912a28` one unreadable sync file discarded the 20-file batch | No 20-file opus/pcm sync batch. Listen codecs are a different door. |
| `52be14b299` clearing a webhook URL must disable it | No developer-webhook routes. |
| `7838af1ca0` SQL injection in `execute_sql` | No `execute_sql` tool. |
| `0a73f38f0c` FastAPI `response_model` 500'd populated memory search | No Pydantic response_model. Memory search is a synthesized page / dark query door. |
| `2879c560e6` chat session counters drifted on clear | No session message-count / preview documents. History is the message store. |
| `1abb045d9a` weekly score window 8 days not 7 | No `get_scores`. |
| `986379077d` empty timezone crashed metadata extraction | No `ZoneInfo('')` on that path. Formation already rejects an invalid timezone. |
| `cca02936bb` Restore RAG context sorting | Test-only in legacy; our packet builder sorts by priority/`sourceId` before join. |
| `232ffe48c7` bound `get_action_items` tool | Already bounded: `GET_ACTION_ITEMS_MAX_ITEMS = 25`. |
| `b31cb004a0` rate-limit window off-by-one | No equivalent sliding window in `apps/service`. MCP rate limit is a port returning `{allowed}`. |
| `ed5a19d278` expired fair-use restriction | No fair-use restriction state machine. |
| `9ee8ea6617` chat quota charged before provider accepts | No desktop chat quota ledger in this tree. |

---

## Coverage statement

**Swept (server-side / domain):** `backend/routers/` (chat, memories, mcp,
mcp_sse, action_items, conversations), `backend/database/` (action_items,
conversations, chat, users), `backend/utils/` (memory, retrieval/agentic,
retrieval/safety, mcp_memories, llm/chat, llm/temporal, conversations/render,
mentor_notifications, sync/files), `backend/models/memory_product.py`.

**Not swept (sibling `legacy-tribal-harvest` or out of this lane):**
`desktop/`, `app/`, `omi/`, `omiGlass/`, `web/` clients, iOS/Android,
platform quirks (`lsregister` / TCC / screencapture), STT/parakeet/VAD
internals, agent-vm/GCE, Cloud Run deploy YAML, CI/ratchets, Stripe billing
beyond noting it is not our door.

**Volume:** `origin/main` since 2026-05-17 contains **14_265** commits and
**5_200** whose subject matched `^fix`. This lane listed **every**
`fix(backend)` subject in that window (~250 lines), then **read 48 commits**
through `log -1` + `--stat` and **deep-read diffs for 22** of those (the set
in the TOC plus the "looked at, not opened" table). A commit that only
renamed symbols, formatted, or unwedged CI was not treated as a fix.

**Shared checkout, start and end:**

```text
$ git -C /Users/dazheng/workspace/omi/upstream-keep-clean rev-parse HEAD
519cf00ba8c664668e74f4e74ab5c9a0060e6c20

$ git -C /Users/dazheng/workspace/omi/upstream-keep-clean status --porcelain
fatal: this operation must be run in a work tree
```

The checkout is bare (`rev-parse --is-bare-repository` → `true`). No
`fetch` / `checkout` / `switch` / `stash` / config write / worktree add was
issued. `HEAD` is unchanged from the start of this lane.

During the sweep, `origin/main` in that shared repo advanced from
`3f5bbcdb` (02:36, the brief's freshness stamp) to
`9d3a0feacff1048e8d1fd99c6e08899125152381` (03:36,
`feat(desktop): install Omi Beta as a sidecar...`). That is a desktop commit
outside this lane. This process did not fetch it.

## Green gates

- `bun run lint:imports` — pass
- `bun run lint:closure` — pass (three production closures, no forbidden substrings)
- `bun test` — 2207 pass, 34 skip, **2 fail**, both
  `apps/service/bin/dev-server.test.ts`, both `failed to bind 127.0.0.1:4851`.
  Isolated re-run of that file: same 2 fail. Holder is `bun apps/service/bin/dev-server.ts`
  pid 65869, cwd `/Users/dazheng/workspace/omi/platform` (the shared checkout this
  lane must not touch), started 2026-08-15 03:01. This lane's only tree footprint
  is this document; the failures do not change with the document. Not killed.
