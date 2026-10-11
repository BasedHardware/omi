# Dream context synthetic evaluation

Run `BACKEND_UNIT_TEST_FILE_LIST=/tmp/dream-context-tests.txt bash backend/test.sh`
with `tests/unit/test_dream_context.py` in the list. All records are invented;
the tests exercise production projection and guard primitives without providers.

Eligibility baseline offers four summary fields across a nonempty movie title
and an eleven-word snippet. The eligibility-aware arm offers one (the empty
overview on the sufficiently long record). Locked offers: **3 → 0**.
This measures deterministic offer eligibility, not model rejection rates or
live quality. Real model behavior and owner dry runs remain separate evidence.
