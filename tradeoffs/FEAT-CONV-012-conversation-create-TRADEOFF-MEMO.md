# TRADEOFF MEMO — FEAT-CONV-012 conversation create/ingest entry

**Audience:** David

**Status:** decision evidence only; **not a proposal accepted into the contract**

**Ruling state:** FEAT-CONV-012 is `open`, decision `defer`; ADR-004 remains accepted

**Spike code baseline:** `ea41f44bb69f04eb12e2bf28b436b98703023b71`

**Contract reference baseline:** `core/foundation` at `2b9fd5d71637f84fd88a3d153b2f1b75f92157ca`

## Decision this memo is meant to unblock

Should the unified conversation contract treat a conversation as:

1. a server-originated record that clients can only finalize/patch/delete;
2. an ordinary ADR-004 client-id-created record whose processing is a later mutation; or
3. a hybrid in which either a client or the capture pipeline may establish identity, with an
   explicit binding rule when both participate?

This spike does not change `ConversationOp`, any router, any adapter, or any storage schema.
Its fixtures are under `omi:spikes/feat-conv-012-conversation-create/` and deliberately fail
closed where the open item requires a human ruling.

## Ruling and implementation constraints

ADR-004 requires each rewritten domain service to provide:

- client-supplied create ids accepting `legacy UUID | word-slug`;
- opId idempotency on every mutation;
- one keyed PATCH whose absent keys remain unchanged;
- an honest `{setVersion, complete, ids}` endpoint;
- keyset list cursors; and
- the shared status classification in which `409` is terminal/permanent.

The current conversation contract explicitly omits create because the legacy entry cannot
honestly implement those create guarantees. That omission is evidence of FEAT-CONV-012, not
permission to invent a fourth write pattern.

The spike did not touch the two other open lifecycle unknowns: cascade-delete defaults
(`UNK-CONV-001`) or abandoned BYOK finalization jobs (`UNK-CONV-003`). It performs no deletion,
data migration, live write, or deployment.

## Current behavior observed

| Observation | Current implementation evidence | Consequence |
| --- | --- | --- |
| `POST /v1/conversations` first resolves the user's current in-progress record, then admits that existing id to processing. | `omi:backend/routers/conversations.py` `process_in_progress_conversation`; `omi:backend/utils/conversations/process_conversation.py` `retrieve_in_progress_conversation` | It is a finalization command, not record creation. After admission it clears the current Redis pointer. |
| Capture/listen already created the conversation before that route runs. | `omi:backend/utils/conversations/lifecycle.py` `create_in_progress_conversation` and recording-session ownership | The server/capture path owns identity before processing starts. |
| `POST /v1/conversations/{id}/finalize` is a newer explicit-id durable admission path. | `omi:backend/routers/conversations.py` `finalize_conversation`; `omi:backend/database/conversation_finalization_jobs.py` | Pipeline entry does not inherently require a mutable “current” pointer, but it still requires a pre-existing record. |
| The finalization outbox is keyed by `(uid, conversation_id, finalization_revision)` and workers are fenced by dispatch generation and lease epoch. | `omi:backend/database/conversation_finalization_jobs.py`; `omi:backend/services/conversation_finalization.py` | Any new create design should reuse this recovery machinery after durable record creation rather than create another processor lease model. |
| Generic `CreateConversation` and external-import processing mint UUIDv4 ids inside `_get_conversation_obj`. | `omi:backend/utils/conversations/process_conversation.py` `_get_conversation_obj` | Server-originated imports cannot currently honor a client record id. |
| `/v1/conversations/from-segments` accepts `client_session_id`, derives a UUIDv5 from `(uid, client_session_id)`, and creates a processing row if absent. | `omi:backend/routers/developer.py` `_from_segments_conversation_id` and `_create_conversation_from_segments` | This is a partial hybrid precedent, but it is endpoint-specific idempotency, not ADR-004 opId idempotency or direct client-id ownership. |
| A stale from-segments claim, or an exception during its processing, deletes the processing row before retry. | `omi:backend/routers/developer.py` `_create_conversation_from_segments` | This recovery behavior must not be generalized into the unified contract; retry should not require destructive record recreation. |
| Processor persistence refuses to recreate a missing conversation and preserves user-owned fields during processing writes. | `omi:backend/database/conversations.py` `persist_processing_result_with_lifecycle` | All options must preserve “processor is not recreate authority” and user-field ownership. |
| The current client contract has patch/delete only, and the legacy adapter has no create wire path. | `omi:core/contracts/src/domain/conversations.ts`; `omi:core/packages/adapters-legacy/src/conversations.ts` | A create variant is a ratchet event and cannot land until this item is ruled. |

## Prototype A — processing-pipeline entry as today

Fixture: `omi:spikes/feat-conv-012-conversation-create/prototypes/pipeline-entry.mjs`

The fixture creates a server-owned `in_progress` record during capture and exposes only a
current-record finalization entry. It demonstrates the important current constraint: there is
nothing an offline create outbox can send before capture has established the record.

### Tradeoffs

- **Identity ownership:** simple and single-owner. Capture/server owns every id.
- **Offline drafts:** impossible as durable conversations. A separate local-only object would be
  needed, with a later alias/import step outside the conversation contract.
- **Pipeline-created records:** native; this is the design's strength.
- **opId:** the current lifecycle no-op behavior is not an opId receipt. A retry can observe state,
  but cannot prove that the same logical request produced it or detect opId reuse with changed
  input.
- **Conflict semantics:** few create conflicts because clients cannot create. The complexity is
  displaced into aliasing any local draft to a server id.
- **Failure recovery:** the current-pointer route loses its retry handle after admission. The
  explicit-id finalization route and finalization outbox are materially safer, but they still do
  not provide create idempotency.
- **Compatibility:** lowest immediate backend migration cost and highest divergence from the
  cross-domain sync contract.

This option needs an explicit ADR-004 exception or a ratified “server-originated record class.”
Without that amendment, calling it conformant would weaken ADR-004 by implication.

## Prototype B — client id plus idempotent create

Fixture: `omi:spikes/feat-conv-012-conversation-create/prototypes/client-id-create.mjs`

The fixture separates durable create from processing. Create accepts a UUID or word slug and
commits an op receipt keyed by opId; processing is a second opId mutation. A repeated opId with
the same fingerprint returns the prior outcome, while changed input returns terminal `409`.

### Tradeoffs

- **Identity ownership:** uniform. The producer calling create owns the id; a server pipeline is
  just another producer and must mint a valid id before capture persistence.
- **Offline drafts:** directly supported. The client can durably queue create before network
  access and refer to the same id in later patches.
- **Pipeline-created records:** supported only if listen/import/merge are migrated to the same
  create service and internal opId discipline. Existing UUIDv4 minting can remain accepted as
  legacy UUID generation, but must move before persistence rather than occur inside processing.
- **opId:** cleanest mapping to ADR-004. A durable receipt can make a lost `201` response harmless
  and reject changed-input replay.
- **Conflict semantics:** same `(uid, id)` with different content is terminal `409`; same opId with
  different content is terminal `409`. Same record id with a new opId and byte-equivalent create
  can safely return the existing record, but David should ratify whether that is allowed.
- **Failure recovery:** create recovery is strong. Processing still needs the existing durable
  finalization outbox; merely retrying inline processing under the same opId can repeat expensive
  work before the receipt commits.
- **Compatibility:** conceptually clean, but it forces every existing record producer through a
  new common create boundary before the backend can claim conformance.

The main risk is treating a conversation like tasks/memories while ignoring that capture creates
identity incrementally and may run before a client has enough content for an ordinary create body.

## Prototype C — hybrid identity with explicit binding

Fixture: `omi:spikes/feat-conv-012-conversation-create/prototypes/hybrid.mjs`

The fixture permits either a client-created `in_progress` row or a pipeline-created row. A
capture can bind to the client id when identity and content do not conflict. If the client and
pipeline carry different non-empty content, or one capture is already bound to another record,
the fixture returns terminal `409`; it does not guess whether to merge, replace, or rekey.

The provisional create/ingest/binding names in code carry
`// domain-pending(FEAT-CONV-012)` markers. They are not proposed contract vocabulary.

### Tradeoffs

- **Identity ownership:** matches reality but is conditional: first durable creator owns the id;
  the other producer must bind to it. That rule and its authorization boundary become part of the
  contract.
- **Offline drafts:** supported without forcing all capture to originate from a connected client.
- **Pipeline-created records:** remain first-class for device capture, import, merge, and recovery.
- **opId:** both client create and pipeline ingest use the same receipt semantics. Internal
  producers need durable opIds too.
- **Conflict semantics:** the most explicit but also the richest: op reuse, record-id collision,
  capture-binding collision, and content reconciliation are distinct terminal conflicts.
- **Failure recovery:** lost replies are recoverable through receipts; processing should still be
  admitted through the existing finalization ledger. Unique capture binding prevents two retries
  from attaching one capture to different conversations.
- **Compatibility:** provides a route for gradually forwarding existing capture and
  from-segments producers into one service, but adds a binding relation and origin provenance that
  option B does not need.

The main risk is institutionalizing two creation modes indefinitely. A hybrid only remains one
contract if both modes call the same create/receipt/lifecycle service and expose the same record
shape; two routers with different semantics would recreate the current divergence.

## Side-by-side comparison

| Dimension | A: pipeline entry | B: client-id create | C: hybrid |
| --- | --- | --- | --- |
| ADR-004 create guarantee | Requires explicit exception/amendment | Direct fit | Direct fit for client mode; pipeline mode must use same service |
| Offline durable record | No | Yes | Yes |
| Existing capture fit | Native | Requires all producers to adopt create | Native through pipeline mode |
| Identity model | Server only | Caller supplied | First durable creator + binding |
| opId receipt | Must be added despite no client create | Natural | Natural but applies to two admission modes |
| Conflict surface | Small locally; alias conflicts move client-side | op reuse + record-id collision | op reuse + record-id + capture binding + content reconciliation |
| Processing recovery | Existing finalization machinery | Existing machinery after create | Existing machinery after create/bind |
| Migration cost | Low | Highest coordinated producer migration | Medium, with higher permanent model complexity |
| Risk of foreclosing offline drafts | High | None | None |
| Risk of permanent dual semantics | Low | Low | High unless one service enforces both modes |

## Data model implications

These names are illustrative only:

```ts
// domain-pending(FEAT-CONV-012): provisional evidence, not a contract declaration.
type ProvisionalCreateReceipt = {
  uid: string;
  opId: string;
  requestFingerprint: string;
  conversationId: "legacy-UUID | word-slug";
  outcome: "committed" | "terminal-conflict";
};

// domain-pending(FEAT-CONV-012): required only by the hybrid option.
type ProvisionalCaptureBinding = {
  uid: string;
  captureId: string;
  conversationId: string;
};
```

Across B/C, the receipt should not store transcript content. Store a canonical request hash,
record id, terminal outcome, and enough response metadata to replay the acknowledgement. The
uniqueness scope should include tenant/user and domain so unrelated producers cannot collide on a
short opId. Retention must cover the longest supported offline retry window.

The authoritative conversation remains separate from:

- operation receipts (request replay authority);
- the existing finalization job (processing lease/recovery authority); and
- in option C only, capture binding (capture-to-record identity authority).

Keeping those authorities separate prevents an op receipt from becoming a second conversation
store or the processing job from becoming recreate authority.

## Failure and retry outcomes that need to be contractual

| Failure | A | B/C fixture result | Production implication |
| --- | --- | --- | --- |
| Create commits, response is lost | Not representable for client create | Same opId returns stored response | Receipt and record write must be atomic. |
| Same opId, changed request | Not detected | `409 op-id-reused` | Matches ADR-004 terminal status classification. |
| Same record id, different create content | Client cannot create | `409 record-id-conflict` | Never overwrite or silently merge. |
| Processor crashes after admission | Current-pointer retry loses handle; stale recovery can close status but not recreate the requested create receipt | Fixture can re-enter, but may duplicate work | Reuse the fenced finalization outbox; do not rely on inline op replay for side-effect safety. |
| Client content and capture content disagree | Alias problem outside contract | Hybrid returns `409 content-reconciliation-needs-ruling` | David must choose reject, replace, or an explicit merge operation. |
| One capture is proposed for two ids | Not exposed | Hybrid returns `409 capture-binding-conflict` | Enforce one unique binding transactionally. |
| Conversation was deleted while processing | Processor persistence is fenced | Must remain fenced | Preserve current “processor cannot recreate” invariant. |

## Migration and compatibility outline

No deletion or incompatible route change is justified by this spike.

1. **Rule the contract first.** Decide A/B/C and the questions below. If A wins, amend ADR-004
   explicitly. If B/C wins, ratify the create shape and conformance fixtures as a standalone
   contract change.
2. **Add conformance fixtures before moving either wire end.** They must cover lost response,
   opId/input conflict, id conflict, pipeline-created records, offline retry, and processor
   fencing. The current patch/delete and incomplete-id-snapshot tests stay green.
3. **Implement one backend create authority behind existing routes.** Keep listen,
   `/v1/conversations`, explicit finalize, developer import, from-segments, sync, and merge
   responses compatible while their internals forward to the common authority.
4. **Treat current `client_session_id` as a compatibility key.** It may map to an internal opId or
   binding during transition, but must not be presented as already satisfying direct client-id
   create. Preserve response ids for released callers.
5. **Move one end at a time.** Only after backend conformance is green should the client contract
   add/create and the legacy adapter stop omitting it. Do not fake create in the adapter by aliasing
   a server UUID; that would preserve the exact gap ADR-004 intends to remove.
6. **Observe adoption before any sunset.** Existing routes and fields remain supported until a
   separately approved DEP record meets its gates. This memo authorizes no deletion.

## Recommendation for David's review (not a decision)

Advance **C, the hybrid, to a contract-decision draft**, while keeping B as the simplicity
benchmark. C is the only prototype that supports offline client identity without pretending the
existing capture/import/merge producers do not create records. However, it should be rejected in
favor of B if the capture client can always supply the final conversation id before the first
durable server write; that fact would eliminate the binding model and make B materially safer.

Regardless of B vs C:

- commit the record and op receipt atomically;
- return terminal `409` for changed-input opId reuse and id/content collision;
- split durable create acknowledgement from asynchronous finalization admission;
- reuse the existing finalization job, lease epoch, and processor fencing;
- preserve processor non-recreation and user-field ownership; and
- do not add `create` to `ConversationOp` until its conformance fixture passes against the chosen
  backend boundary.

## Questions David must answer before implementation

1. Can a conversation exist durably with no transcript segments yet, or must offline create carry
   at least one segment?
2. If a client-created id exists before capture, must capture adopt it as canonical, or may the
   server return an alias to a pipeline id?
3. Can every capture producer receive/propose the final record id before its first durable write?
   If yes, is there any remaining need for hybrid mode?
4. When the same record id arrives under a new opId with identical create content, should the
   server return the existing record or require the original opId?
5. When client and pipeline content disagree, is the correct result fail-closed `409`, replace,
   or a separately authorized merge operation?
6. Is create only a durable record write followed by a separate finalize mutation, or does create
   also admit processing? The latter makes a lost response harder to distinguish from long-running
   processing.
7. What is the op receipt uniqueness scope and minimum retention window for offline clients?
8. If A wins, what exact ADR-004 amendment defines the server-originated-record class and explains
   why conversations alone do not support offline create?

## Verification evidence

- Disposable spike tests: 7/7 pass with Node's hermetic test runner.
- Executable demo: all three prototypes run and emit their record/outcome shapes.
- Existing `core/foundation` conversation adapter contract tests: 11/11 pass after building the
  testkit dependency slice; they continue to prove that the live contract has patch/delete only.
- Focused current-pipeline tests: 16/16 pass across from-segments idempotency and synchronous
  processing-admission rollback.
