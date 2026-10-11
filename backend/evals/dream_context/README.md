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
