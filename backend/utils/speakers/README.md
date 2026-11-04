# Speaker identity package

Speaker evidence, private profile policy and presentation share this package.
The conversation adapters coordinate inference; database modules own durable
consent, source, deletion and manual-assignment authority.

| Module | Responsibility |
| --- | --- |
| `policy.py` | Versioned acoustic operating points and evidence eligibility. |
| `evidence.py` | Build ranked evidence and project labels through manual receipts. |
| `processing.py` | Finalization orchestration, evidence publication and cohort projection. |
| `refinement.py` | Bounded vector refinement and PCM measurements. |
| `context.py` | Contextual hypotheses and roster counts. |
| `provider_partition.py` | Preserve the provider's original acoustic partition. |
| `embedding_cache.py` | Bounded process-local clip embeddings. |
| `auto_enroll.py` | Explicit-label contribution policy and per-person sealing codec. |
| `person_pool.py` | Reversible confirmed-person voiceprint contributions. |
| `recurring_voices.py` | IO-free recurring profile qualification, joint matching, refresh and retraction. |
| `display.py`, `display_metrics.py` | Conversation-wide presentation and its count guard. |
| `__init__.py` | Package boundary. |

Recurring profiles enter only through the successful batch final-pass adapter
in `utils/conversations/final_pass_batch.py`. The sealed store and transactional
confirmation bindings live in [database/recurring_voices.py](../../database/recurring_voices.py)
and [database/recurring_voice_assignments.py](../../database/recurring_voice_assignments.py).
Unconfirmed profiles carry a private recurring ID; manual confirmation supplies
a person binding. Live/sync voiceprint loading keeps its existing roster.

Retention, thresholds and rollout ownership: [ADR-0008](../../docs/adr/0008-recurring-batch-voices.md).
Verification uses the [backend runners](../../AGENTS.md#testing), including the
recurring-policy, strict-transaction, assignment and batch-final-pass unit suites.
