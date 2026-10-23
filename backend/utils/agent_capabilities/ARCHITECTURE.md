# Owner-scoped agent capabilities

The authenticated caller supplies an owner UID and explicit `authority`. A model
cannot change that authority through tool arguments. `user` carries the signed-in
owner's current request and applies guarded edits with journal/Undo; `dream`
stages work for Dream's independent verifier and Review policy. Chat mounting is
outside this PR.

An explicit user mutation carries a temporary owner-scoped authority through
the journal writer even when autonomous Review admission is disabled. It grants
no access to another owner and ends with the mutation. User edits keep source, generation and session edit caps; autonomous suppression and cleanup protections apply only to Dream. Immediate apply does not
turn a shared session into an unbounded write loop.

| Module | Responsibility |
| --- | --- |
| `session.py` | Seen refs, budgets, precise tool results, resubmission and the sanctioned shaped-agent loop; applies the harness tool design rules (`utils/llm/ARCHITECTURE.md`): context-window default for temporal search, `Z` times, declared argument aliases |
| `limits.py` | Caller-supplied bounded resource limits (Dream bucket policy lives in `config/dream_session.py`) |
| `search.py` | Owner-scoped lexical, semantic and temporal discovery with opaque cursors |
| `reads.py` | Decrypted records behind visibility, lock and source-generation boundaries |
| `evidence.py` | Snapshot container; session roles stay outside persisted records |
| `staging.py` | Immediate schema, evidence, suppression, current-snapshot and byte guards; no writes |
| `guards.py` | Shared deterministic quality and eligibility checks |
| `errors.py` | Stable non-content mutation errors shared with HTTP boundaries |
| `effects.py` | Explicit authority and verification boundary for staged effects |
| `registry.py`, `kind_schema.py`, `kind_keys.py`, `kind_views.py` | One declaration per kind selects schema, validation, semantic key, apply, Undo, display, allowed fields and default policy |
| `tools.py` | Reversible domain mutations and Review acceptance through existing writers |
| `cleanup_edits.py` | Protected tasks/people, same-speech duplicate links and language guards |
| `change_view.py` | Before/after and surrounding speech for the encrypted change receipt |
| `text_edits.py` | Pure exact-term replacement with no storage or agent dependencies |
| `transcripts.py` | Immutable captured text, encrypted correction overlays and read/storage projections |

Tool schemas and uniform `collection/id#segment` refs live in `models/agent_tools.py`,
`models/agent_edit.py` and `models/agent_refs.py`. New sessions canonicalize legacy `memories/` aliases to `memory_items/`; stored receipts remain readable. Search grants a ref; full read
grants a record snapshot. Search debits only the hit payload the model receives
(ref and snippet). Hydration that builds that snippet is bounded to the fields
the snippet and filters need and does not consume the session read-byte budget.
`read` is the call that debits a full record. A missing, hidden, or locked row is
skipped, counted, and reported as unavailable; it does not discard the rest of
the page. A transient hydration failure degrades that search path, so the
result is incomplete and retryable. History pages and seeds yield readable owner-visible
records, paging past ids that no longer resolve. Legacy `memories` is the
`memory_items` collection at the ref boundary. Staging rechecks the snapshot and captures storage fences. Domain
writers recheck those fences in the transaction that journals the effect. Dream
also checks its live owner lease and global kill switch inside that transaction.

`database/review_transcript_changes.py` commits overlay entries and any generated
summary patch with the journal. The conversation read boundary renders active
corrections from an encrypted inline copy and exposes original text alongside the projection. Reads fall back to captured speech with a counter on unavailable or invalid overlays; transactional mutation paths remain strict. Storage encoding
restores captured text. Undo marks overlay entries inactive and checks speech
anchors and newer dependent edits; historical in-place receipts retain their
existing reversal path. The existing manual segment-edit API creates a user
correction through that same writer, even when autonomous Review is disabled.
Summary source references and cached client processing are invalidated in the
same commit. A newer correction that depends on an older one prevents reversing
its input underneath it. Late client output binds to the rendered transcript in
a transaction that also reads the overlay; changing captured bytes is not needed
to reject a stale summary. Pure field-presence helpers and exact-term replacement
are separate from domain mutations so these read boundaries do not import the
entire write stack.

Dream owns scheduling, admission, prompts, verification decisions, demotion,
attention ranking and counts-only telemetry outside this package. The capability
layer never chooses a provider or owns background-job cadence.

Dream injects its instructions, seed, low-value question policy and Review queue/ranking from `utils/dream_instructions.py` and `utils/dream_review_policy.py`. Tool failures carry `code`, `field`, `ref`, `expected`, and `retryable`; infrastructure failures are non-retryable.
