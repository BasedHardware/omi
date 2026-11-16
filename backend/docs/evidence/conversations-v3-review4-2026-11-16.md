# Conversations v3 — round 4 personal context

Repository BasedHardware/omi, branch lane/conversations-v3, parent 60ecfe76fbd.
Local synthetic work only. No GCP tier, production access, private data, push,
PR, merge, deployment or external runtime flag/config change.

## Decisions and implementation

- R4-1: Every v3 summary reaching the notes seam gathers the existing
  `composer_context.gather` account pack. Its existing eight-second deadline,
  read budgets, relevance/quality filters and fail-empty behavior remain the
  authority. Profile, active goals, transcript-bound people and ranked memories
  render through `meeting_context_render`'s BACKGROUND CONTEXT block. Owner
  corrections survive. Short/hidden/already-covered rows do not gather a pack.
  The one-shot notes writer, streaming, gateway/metering, Flex-first background
  and Standard foreground paths are unchanged; no notes agent loop is restored.
  `meeting_context_override` previously accepted calendar metadata only; it now
  also accepts a pre-rendered text override, without treating it as calendar data.
- R4-2: One optional context gather per reconciliation, at most one second and
  53 documents (one profile, twenty already-bound people, thirty-two title
  candidates). Shared context executor has no queue; caller timeout discards late
  results. Bound speaker names are filtered again per stretch. Earlier titles
  use the owner's local calendar day (UTC fallback), exclude future/current
  rows and product-hidden/deleted/locked/private/merged/capture rows. The
  title-only query uses the existing single-field started_at index. No new
  composite index: the manifest remains 304 composites.
  `CONVERSATIONS_V3_OUTLINE_CONTEXT=off` is a default-on, code-local kill switch
  for the extra reads; it requires no config change to ship. No stage is moved.
- R4-3: Cache and paid-attempt identity hash the context version, transcript
  fingerprint and complete effective messages, including SYSTEM_PROMPT and
  preceding-conversation evidence. Identical effective input reuses the outline;
  a prompt, context or context-version change does not reuse a stale paid result.
- R4-4 (optional, omitted): `models/structured.py:Structured.Participant` has no
  person_id field. Adding it changes the shared notes output schema and generated
  clients for legacy/non-v3 writers too; storing an extra raw key alone loses it
  at typed reads. That exceeds the cheap planner-only linking scope. Existing
  authoritative person IDs remain on copied transcript segments; no speculative
  name-to-identity binding is introduced.

## Cost boundary

Actual o200k_base measurement on one deterministic synthetic greenhouse example:
**108 added summary input tokens**, **46 added outline input tokens**. These are
an example, not production averages, model quality results or latency estimates.
Hard caps including the added block's headings: **2,000 tokens per summary**
(profile/goals/people allocation 600; memory/background allocation 1,200 before
rendering) and **320 tokens per outline**. UTF-8 byte fallback is conservative.
There are zero added writer model turns. Existing composer retrieval/embedding
work is reused; this is not a claim of zero retrieval/vendor cost.

Context alone never schedules another summary. The existing late-audio rule
stays once-only, new nonduplicate speech >=100 words or 10%, within a day.
Keep the rollout churn spending criterion <=5%; existing first-write/rewrite
counters and metered gateway usage must verify it before expansion. No production
churn ratio or cost saving was measured here. The one-second outline read
allowance is why its separate reversible kill switch is provided.

## Explicit follow-ups outside this PR

- V3-MOMENT-MARKERS: generalized recording cut input plus third double-tap action.
- V3-SECTION-START-TIMES: per-section start times.
- REVIEW-BACKGROUND-FREE-TEXT: free-text background question kind in Review.
- Participant person-ID schema/linking can be considered separately with the
  shared notes schema owner; it is optional in this round.
- V3-BACKFILL-30D-PARTITIONS remains required before enabling the off backfill.

## Verification

Final exact commands and results follow below.
Test inventory: conversations-v3-review4-tests.txt. Initial development run
caught fixture omissions (required structured/is_user and a UTC-day assumption);
these are corrected and not counted as passing evidence.

The required scope panel scope-20261116t133550-57fa returned no terminal answers
before its deadline. All three lanes were stopped. agentctl cancellation returned
cancel_owner_stale repeatedly; kernel-verified exact owned native process groups
and orphaned owner PIDs were terminated, then agentctl terminal state was collected.
No scope finding or independent SHIP review is claimed. Its disposable checkout
was removed by the panel collector; no unrelated checkout was touched.

## Round-4 final verification receipt

Source commit: bd8632ab08f9aa53f682a3a38a990f5ea5af2b9b.
The documentation receipt commit changes no runtime or test code.

Backend commands (one pytest process per file; pinned worktree venv;
all under the managed heavy gate):

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review4-pytest-xml \
  BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review4-tests.txt \
  BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review4-pytest-xml \
  BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review4-focused-tests.txt \
  BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
```

The full 35-file run had 3,715 passing tests and exposed one new driver fixture error (factory instead of
copied budget object). The corrected 14-file focused/Firestore rerun passes
**1,081 tests**, including all touched test files and seven Firestore guards.
Latest per-file JUnit receipts over the 35-file inventory total **3,717 passed**,
including **190 focused v3**, zero remaining failures, errors or skips. These are
a union of the full run plus the corrective rerun, not an assertion that the
initial full command exited zero. The new context file has 12 passing tests.
Logs: review4-final-tests.log, review4-focused-tests.log; review4-junit/ and
review4-counts.json under the prescribed brief directory.

Other exact commands:

```sh
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --write
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --check
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all --check
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py --check
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py --check
/Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-ref origin/main
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env PYRIGHT_PYTHON_FORCE_VERSION=1.1.403 backend/.venv/bin/python -m pyright -p backend/pyrightconfig.json --pythonpath backend/.venv/bin/python --level error
/Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils backend/dependencies.py --diff-base 92b697098eb6ff200165cf005577c916aeab189f --fail-on high_network_io,async_helpers_with_blocking,time_sleep,mixed_await_sync_db,no_await_should_be_def,unmanaged_thread_offload
backend/.venv/bin/python backend/scripts/check_conversation_readers.py --inventory
scripts/pr-preflight --metadata-only --pr-body-file /Volumes/Ephemeral/scratch/episode-dayparts-brief/PR-BODY-V3.md
```

All pass: generated OpenAPI/Dart/TS/Swift outputs are byte-identical; additive
compatibility preserved; typecheck zero errors; async gate zero selected
findings; reader audit **491 references**; PR metadata **five checks**.
No schema change in this round. Read-only merge-tree is clean against
origin/main 6ecaf35e39b4b726d77a2da2880f3c39166e26b0; no actual merge/rebase or
combined-runtime acceptance is claimed.

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  PATH="/Volumes/Ephemeral/scratch/conversations-v3-flutter-3.44.5/flutter/bin:$PATH" \
  OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/episode-dayparts-brief/PR-BODY-V3.md \
  make preflight
```

Exit 0: **81 checks passed in 510.14 seconds**, including 75 Python checks,
607 Firestore shape tests, 73 plugin-transport tests, web typecheck and
1,079 Vitest plus six Bun tests, five admin tests, runtime-env composition and
desktop formatting/lint. Source and PR body stayed frozen throughout.
Receipt: review4-preflight-frozen.log.

Not run: production/private-data reads, live model quality/cost/latency or churn
measurement, dev end-to-end, released-device acceptance, emulator contention,
image build or combined lead/Q12 runtime qualification. The <=5% churn rollout
criterion remains a measured rollout gate, not a synthetic-test claim.
