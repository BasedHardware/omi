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

Vocabulary laundering and case-only changes have synthetic regressions. Only user-authored or accepted vocabulary with independent evidence may support automatic spelling; all new vocabulary is Review-only.
`test_dream_retrieval_diagnostics.py` reproduces the initial four-target cap,
a fabricated context-probe rejection, and 35 reads with only three visible
targets. It checks unused-budget recovery, no unavailable/unread acknowledgement,
all four retrieval paths (including failures and duplicates), closed metric labels,
and the counts-only `utils.dream_agent.dry_run_retrieval` with admission, settlement
and inference forbidden. The runbook gives the owner pod invocation. These are
synthetic contract checks; they do not attribute a production empty-result path.
