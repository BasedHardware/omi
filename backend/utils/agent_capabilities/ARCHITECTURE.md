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
existing reversal path.

Dream owns scheduling, admission, prompts, verification decisions, demotion,
attention ranking and counts-only telemetry outside this package. The capability
layer never chooses a provider or owns background-job cadence.
