# Dream context synthetic evaluation

Run `BACKEND_UNIT_TEST_FILE_LIST=/tmp/dream-context-tests.txt bash backend/test.sh`
with `tests/unit/test_dream_context.py` in the list. All records are invented;
the tests exercise production projection and guard primitives without providers.

Eligibility baseline offers four summary fields across a nonempty movie title
and an eleven-word snippet. The eligibility-aware arm offers one (the empty
overview on the sufficiently long record). Locked offers: **3 → 0**.
This measures deterministic offer eligibility, not model rejection rates or
live quality. Real model behavior and owner dry runs remain separate evidence.

Context cases assert target/context roles in both real planning stages, reject
an attempted context edit and a context merge operand, include rare-token and
vocabulary near-matches, and stop lazy retrieval at the full-payload budget.
Retrieval tier tests exercise owner-scoped linked, lexical, semantic and temporal
providers with synthetic responses. `utils.dream_agent.dry_run` is the owner
entrypoint documented in the Dream runbook.

Spelling regressions run through `test_dream_grounding.py` and the real two-stage
dry-run function. An invented, explicitly confirmed film name used to accept an
unsupported correction automatically: **ungrounded auto-applies 1 → 0**;
**Review spelling questions 0 → 1**. Cited independent spelling and persisted
vocabulary still permit automatic correction. Derived facts and substring or
accent-insensitive matches cannot authorize it. These are deterministic scripted
model-response comparisons, not measured live-model accuracy.


Older-data signal replay (`test_dream_cleanup.py`): an old task, a near-duplicate people pair, a near-duplicate private memory pair and an eligible empty conversation are absent from a dirty-only pass (0 reachable signals). Weighted history seeding makes all six records eligible (scores 2,3,3,3,3,2); duplicate operands are admitted together. A review less than 30 days old suppresses every candidate. These are deterministic retrieval/guard findings, not model precision claims.

The epsilon branch draws a uniform global rank across owner-scoped collection counts, hydrates one record, and does not redraw after visibility/age/cooldown rejection. For a stable population every stored record has the same draw probability. Concurrent writes may change counts/ranks; report random-source counts separately. Firestore offsets bill skipped reads, so this is not a constant-cost sample; RPCs have 3-second deadlines and default epsilon is 10% of the default 10% backfill attempts. Set the random share to zero to disable that cost.


Owner pod dry-run (caller supplies already authorized decrypted records; no user reads or product writes inside the function):

```python
from utils.dream_agent import dry_run
result = await dry_run(uid, records, targets=target_refs, vocabulary=persisted_vocabulary)
# result: plan including auto/suggest policy, guard_decisions, role_counts, tokens
```

Use synthetic `turn` injection for provider-free replays. With the default turn this uses ordinary gateway inference and accounting. Inspect the returned plan in the owner's secure session; only aggregate counts belong in PRs/docs.
