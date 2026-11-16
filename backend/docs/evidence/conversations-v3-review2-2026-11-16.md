# Conversations v3 review round 2 — 2026-11-16

Baseline: edc4e0d9dc2 on lane/conversations-v3. Local source/synthetic evidence
only. No production/private user data, GCP credential tier, push, PR, merge,
rebase, deploy or external runtime configuration change.

## Decisions and implementation

- David manual intent: planner persists manual_end across late rewrites and
  finished-window preservation; product merge carries it and processes it even
  when reprocess:false. Historical derivation uses the same planner. Any speech
  is visible and fully summarized regardless of length, except media/recognized
  background. No speech still creates no window. Manual intent bypasses the
  processing <20-word and short-task paths and content/quiet minima. A newly
  received manual end invalidates old summary coverage even without new words.
- Q1: both tile_state contracts add failed and repository generators update
  OpenAPI, Dart, TypeScript and Swift. Exhausted processing/outline work and
  affirmative transcription failure produce completed/failed with retry metadata.
  Failed v3 rows remain Home-visible under home_hidden; deleted, discarded and
  recording guards still apply. Locked rows retain locked presentation.
  Partial/unproven capture alone is recoverable, not an affirmative failure.
  Product reprocess owns the copied conversation window, renews its lease,
  resets its bounded attempt budget, bypasses covered/short notes and notes-hash
  reuse, and uses Standard. It writes writing then done/failed; returning without
  a successful persisted write fails. Successful foreground notes clear failure.
- Q2: background hides only if a contributing recording recognizes the wearer
  via is_user:true or an actual segment-bound wearer label from the authoritative
  speaker evidence/manual-assignment projection. Recognition is over the whole
  contributing recording, as requested. Uncertainty changes effective kind to
  conversation, using the normal 300-word threshold (manual intent overrides it).
  Media remains hidden. outline_kind retains the original model classification;
  home_hidden_reason retains the decision. A no-label builder counter,
  omi_conversations_v3_uncertain_recognition_shown_total, counts committed first
  exposure/transitions into the fallback, without double counting repeated work.
- A4: CONVERSATIONS_V3_FIRST_APP_BUILD stays unset in source. Lead2 sets it at
  rollout through the shared runtime source from the first TestFlight build
  containing this PR. Unknown cannot qualify episode-deletion evidence.

Q2 is applied before manual intent: unrecognized background becomes conversation,
so a manually ended such window is visible. Positively recognized background and
media remain hidden. This follows both lead decisions without a second app change.
The existing notes prompt, sync merge, entitlement and downstream effect rules
are retained. Lifecycle writer inventory entries were reviewed and updated for
new payloads and previously stale round-1 v3/playback declarations.

## Discriminatory regression coverage

- test_conversations_v3_engine.py: 5/40-word manual ends, sticky late rebuild,
  no-speech/no-window, media/recognized background hidden, uncertain background
  visibility versus recognized background and normal short threshold.
- test_conversations_v3_review.py: actual 40-word manual processing including
  backfill, unchanged-word manual promotion owing notes, product merge carrying
  manual intent, terminal outline/transcription failure and immediate failure
  before silence, authoritative bound/ineligible/stale identity evidence,
  uncertain-exposure counter and unchanged-projection deduplication.
- test_conversations_v3_stream.py: 5/40-word manual captures reach actual
  _get_structured notes seam with bodies/title; real decorated product reprocess
  uses its own transcript with Standard, bypasses covered short notes, and
  persists writing -> done/failed, including exception/no-write outcomes.
- test_conversations_v3_transactions.py: exhausted attempts, explicit Retry
  resets the budget and locked presentation is not replaced by failed.
- test_home_feed.py: failed visible v3 rows survive legacy failure/noise filters;
  hidden v3 and failed legacy rows preserve their respective policies.
- test_lifecycle_state_table_writers.py: exact reviewed payload/terminal writer
  declarations for v3 processing, builder, planner and playback projection.

## Commands and receipts

Final focused and touched selection: conversations-v3-review2-tests.txt, 23 files.

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review2-pytest-xml \
  BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review2-final-tests.txt \
  BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
```

The wrapper uses the pinned Python 3.11 and only adds per-file JUnit output;
backend/test.sh retains its isolation and timing guards. Final receipt is in
the requested PR body and local review2-final-tests.log, with JUnit receipts.
Final pass: 2,631 passed / 23 files / 0 failures, errors or skips, including
162 focused v3 cases and the immediate-transcription-failure regression.

Repository generation and additive checks (all passed):

```sh
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --write
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --check
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all --check
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py --check
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py --check
backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-ref origin/main
```

Dart decoder check from app/: omi-heavy run -- flutter test
 test/backend/conversations_v3_decoder_test.dart: 3 passed.
Reader audit: backend/.venv/bin/python backend/scripts/check_conversation_readers.py
 --inventory: 490 references classified. Pyright from backend/: omi-heavy run -- env
 PYRIGHT_PYTHON_FORCE_VERSION=1.1.403 .venv/bin/python -m pyright -p
 pyrightconfig.json --pythonpath .venv/bin/python --level error: 0 errors.

Required frozen committed-head verification command:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/episode-dayparts-brief/PR-BODY-V3.md \
  make preflight
```

Final head and exact preflight receipt are appended to the requested PR body and
outcome record after the runner exits; no tracked report changes while it runs.
Round-1 broad, audio and old-client evidence remains in
conversations-v3-review1-2026-11-16.md. This round does not claim a new all-green
394-file run or device acceptance.

## Scope and limits

Required scope panel: scope-20261116t113404-67fb. One returned; two exceeded the
bounded deadline and were cancelled. All executions are terminal. Accepted
actual risks: Retry no-op, Pydantic field preservation, Home failure filtering,
manual merge processing, original-kind retention, counter idempotence and
lifecycle inventory. Rejected the speculative absence of frontend support:
the lead explicitly reports its app branch already handles failed/home_hidden.
Rejected treating partial/unproven tail alone as terminal: current affirmative
failure receipt semantics permit repair. No speculative new rollout flag was
introduced against the lead's decided reversible fallback. This limited scope
is not full independent review. No PR exists, so no PR panel was run.

Released-device playback/export and live dev/WAL/share/delete acceptance remain
with the lead. No paid model or production call was used. Backfill remains OFF;
V3-BACKFILL-30D-PARTITIONS remains necessary before the 30-day deletion gate.
