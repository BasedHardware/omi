# Owner-scoped agent capabilities

The authenticated caller supplies an owner UID and explicit `authority`. A model
cannot change that authority through tool arguments. `user` carries the signed-in
owner's current request and applies guarded edits with journal/Undo; `dream`
stages work for Dream's independent verifier and Review policy. Chat mounting is
outside this PR.

| Module | Responsibility |
| --- | --- |
| `session.py` | Seen refs, budgets, precise tool results, resubmission and the sanctioned shaped-agent loop |
| `limits.py` | Bounded session resource profiles |
| `search.py` | Owner-scoped lexical, semantic and temporal discovery with opaque cursors |
| `reads.py` | Decrypted records behind visibility, lock and source-generation boundaries |
| `evidence.py` | Snapshot container; session roles stay outside persisted records |
| `staging.py` | Immediate schema, evidence, suppression, current-snapshot and byte guards; no writes |
| `guards.py` | Shared deterministic quality and eligibility checks |
| `effects.py` | Explicit authority and verification boundary for staged effects |
| `tools.py` | Reversible domain mutations and Review acceptance through existing writers |
| `cleanup_edits.py` | Protected tasks/people, same-speech duplicate links and language guards |
| `change_view.py` | Before/after and surrounding speech for the encrypted change receipt |
| `text_edits.py` | Pure exact-term replacement with no storage or agent dependencies |
| `transcripts.py` | Immutable captured text, encrypted correction overlays and read/storage projections |

Tool schemas and uniform `collection/id#segment` refs live in `models/agent_tools.py`,
`models/agent_edit.py` and `models/agent_refs.py`. Search grants a ref; full read
grants a record snapshot. Staging rechecks it and captures storage fences. Domain
writers recheck those fences in the transaction that journals the effect. Dream
also checks its live owner lease and global kill switch inside that transaction.

`database/review_transcript_changes.py` commits overlay entries and any generated
summary patch with the journal. The conversation read boundary renders active
corrections and exposes original text alongside the projection. Storage encoding
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
