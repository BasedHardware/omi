# Token lease review corrections

This supersedes the append/recovery descriptions in the earlier
[Part A receipt](2026-11-09-record-token-lease.md). Lead decisions A/B/C apply
to the FIX-FIRST correctness and custody reviews of `8ab8444009ec`.

The monitoring findings are already resolved: the two split alert objects are
in the aggregate, the three source metrics are declared in the production
inventory, and the seal worker's literal oldest-age Gauge is exported by its
HTTP registry. Mirror, source-emitter and endpoint tests cover these contracts.

## Custody ordering and retries

Serve-cohort uploads acquire a request-specific `custody:<job_id>` token before
local staging or archiving. It carries `signal_source=custody_append` and its
own lease. This changes neither the partial marker nor upload revision. A
concurrent partial pass must refuse while the token is live, and any old
admission/plan CAS must re-read the token map.

Only an accepted response with durable archived bytes bumps
`record_upload_revision` and clears that exact token. A refused/failed upload
(including 202/failed) clears only its token, without revision or late-counter
changes. A lost token cannot produce a successful ACK: the phone keeps its WAL
and retries under a fresh fence. A crash leaves the token protected by its own
lease. Other uploaders' tokens are never cleared.

Memoized waits return before token acquisition or renewal. Manifest heartbeats
and completed durable per-file archive appends renew existing clocks at most
once per lease/2 per conversation. A later upload's new token cannot postpone
renewal of an older live uploader. There is no idle timer. The two per-upload
fence create/finalize writes are custody transitions, separate from throttled
heartbeat renewal writes. Late-append counters are emitted only after accepted
durable append completion; shadow counts accepted late appends without reopening.

## Late audio and named exits

Late owner WAL holes are decoded and retained create-only against the actual
retained reference coverage. This supports partial rows and interior gaps,
unlike the existing tail-only gap-fill path. The normal partial worker sees
the new chunks. A conservative 503 can still retain chunks while the phone
keeps its WAL: the partial inventory is explicitly re-armed and its old CAS
invalidated, without bumping upload revision or counting that refused request.
The WAL inventory shares the partial worker's existing MAX_SOURCES bound (8192).
Original raw archives and original retained chunks are never deleted/overwritten.

Serve-only frames on a complete seal, including a fresh socket mint before any
renewal, reopen `record_audio_closed=false`, restore the exact socket token with fresh clocks, bump revision and increment late_append.
The existing partial continuation processes newly retained audio, including an
interior gap when the old tail already reached finished_at. A distinct durable
coordinator preserves completed/leased original work and immutable projection
bindings. A not-yet-admitted original pending obligation is reused instead.
Continuation waits for an older full intake's completed publication ledger;
an older full projection cannot overwrite a newer partial interior fill.
It uses the same privacy, payer, admission and annotated-text guards
as ordinary partial continuation. No completeness is invented: recovery carries
a partial marker and retains the existing partial continuation/retirement exits.
Off remains the old path; complete-seal shadow frame observations only count.

Named exits remain seal, partial_finish and reactivated. Custody reactivated now
means begin fence followed by durable finish; frames reactivated may schedule
partial continuation. Its record_pending exit is the existing partial worker;
unchanged inventories poll hourly and retire after the existing 24h idle window.
No Part B discovery or index implementation is added here.

## Validation

Recorded 2026-11-09T02:44:04+00:00 on branch
`lane/tokenlease`, code head `a3e347e1b8438f1cafb3ad7e5bcb46ab880cd7ae`, rebased onto freshly fetched main
`42448d34a441c3f7d64591190b466ab94ce260eb`. The later receipt-only commit is reported separately in the handoff.
All final commands below ran serially without source changes during the final
closeout. This is local validation, not CI, production acceptance or a deploy.
GCP tier: **none**. No push or PR.

Heavy admission and child commands:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 -- python3 /Volumes/Ephemeral/scratch/tokenlease-review-closeout.py
# Each unit suite below runs in its own interpreter, cwd backend:
.venv/bin/python -m pytest -q --tb=short tests/unit/<suite>
# Root; private emulators, OMI_REQUIRE_STORE_BACKENDS=all:
env -u TOKENLEASE_RETRY -u TOKENLEASE_VALIDATE_HELD_ONLY python3 /Volumes/Ephemeral/scratch/run-tokenlease-local-validation.py
# Inside firebase emulators:exec --only firestore --project demo-omi-listen-stack:
.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py
.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir /Volumes/Ephemeral/scratch/tokenlease-validation-zvewnq8n/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py
# Root, OMI_PR_BODY_FILE=.agent-brief/tokenlease-pr-body.md:
make preflight
```

Every test launcher removes GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_*
variable, service-account/auth-file variables and external PostgreSQL bindings.
Private HOME/config/TMP prevent ADC fallback. Unit/preflight stage overrides are
unset; integration uses offline with the Firestore demo project on loopback and
fixture-owned PostgreSQL. Firebase shares emulator binaries only, not config or
credentials. No backend stage env files exist in this worktree.

| Unit suite | Exact final result |
| --- | --- |
| `test_record_token_lease.py` | 77 passed |
| `test_record_custody_append.py` | 15 passed |
| `test_record_lease_append.py` | 1 passed |
| `test_record_producer_proof.py` | 27 passed |
| `test_record_seal_repair.py` | 48 passed |
| `test_record_partial.py` | 78 passed |
| `test_pusher_record_abandon.py` | 24 passed |
| `test_record_pending_repair.py` | 63 passed |
| `test_record_audio_seal.py` | 57 passed |
| `test_record_seal_cluster_repair.py` | 121 passed |
| `test_record_seal_nojob.py` | 44 passed |
| `test_refactor_modes.py` | 17 passed |
| `test_lifecycle_state_table_writers.py` | 1738 passed |
| `test_record_token_lease_deploy.py` | 8 passed |
| `test_monitoring_telemetry_contract.py` | 52 passed |
| `test_sync_v2.py` | 181 passed |
| `test_record_seal_worker.py` | 20 passed |
| `test_record_seal_worker_deploy.py` | 7 passed |
| `test_record_seal_cluster_repair_deploy.py` | 10 passed |
| `test_record_seal_worker_guards.py` | 13 passed |
| `test_monitoring_alert_backtest.py` | 29 passed |
| `test_monitoring_notification_contract.py` | 8 passed |
| `test_monitoring_alert_rule_contract.py` | 75 passed |
| `test_record_gap_fill.py` | 52 passed |
| **Total (24 suites)** | **2,765 passed; no failures, skips or xfails** |

| Integration / gate | Exact final result |
| --- | --- |
| Held custody, all three store backends | 75 passed |
| Recovery custody, all three store backends | 39 passed |
| Emulator lifecycle scenarios/properties | 34 passed, 3 pre-existing xfailed |
| Named lease exits: seal / partial_finish / reactivated | All three passed |
| Expanded local lane via final make preflight | **56 unique checks passed**, exit 0 |
| Append-only monitoring shape / protected paths / git diff --check | Passed |

The final log is `/Volumes/Ephemeral/scratch/tokenlease-review-fixes-results.log`.
The emulator config is `/Volumes/Ephemeral/scratch/tokenlease-validation-zvewnq8n/firebase.json`; processes are stopped after the
run. Disposable scripts/log paths are included for inspection; commands and exact
results are preserved here independently of those scratch files.

The earlier explicit expanded run selected the same 56 checks:

```sh
backend/.venv/bin/python .github/scripts/run_checks.py --lane local --base 42448d34a441c3f7d64591190b466ab94ce260eb --head HEAD --changed-files /Volumes/Ephemeral/scratch/tokenlease-review-fixes-changed-files.txt --pr-body-file .agent-brief/tokenlease-pr-body.md --keep-going
```

Its three failures were addressed without waivers: the recovery helper now
uses the shared immutable-policy/first-writer fallback; the draft discloses the
shared partial MAX_SOURCES bound (8192) and named exits; and the sync line-count
declaration matches the rebased target (3819 to 3841). All three named checks
passed, then the final full 56-check run passed. No policy-guard exception,
review-date extension, assertion suppression or new xfail was added.

Initial unit failures were corrected: the seal-race assertion now proves fence
before bytes and revision after acceptance; the alert assertion checks the
approved exact increase expression and aggregate mirror; test-name/setup errors
were corrected. One existing 0.3-second child-start checkpoint test missed its
checkpoint under load; it was rerun unchanged and the entire final 121-test
cluster suite passed. The final uninterrupted 24-suite run is fully green.

## Boundaries and remaining acceptance

Correctness review items 2/3 are confirmed closed by the aggregate mirror,
source-emitter declaration and worker HTTP metrics tests. All other reviewed
items are fixed, including the fresh-socket mint path and ordering behind older
full publication. The complete-seal and discovery function ASTs match pinned
main; no index changes or Part B work are introduced by this branch. Main's
independently merged #24953 age-order discovery is preserved.

No edits to users.py, live.py, ProjectionReleaseStore or held_dead_letter files.
The alert aggregate and metric inventory still contain only the previously
approved append-only additions, preserving main's existing entries and values.
The set_record_upload_pending edit is confined to the existing producer-token
transaction: its off-mode payload is exact, and serve-only recovery joins that
transaction before writes. seal_record_audio is unchanged.

Recovery uses the existing partial continuation, not a reset of original
immutable units. It deliberately carries a partial marker and waits for any
older full publication. Existing privacy/payer refusals and inventory/storage
bounds remain fail-closed with raw audio/WAL retained. No reviewed correctness
item remains unfixed. Production signal-gap measurement, 48h shadow soak and
lead2/P4 ramp acceptance remain unperformed; defaults stay off.

## Local review-fix commits

Rebased commits before the final receipt-only commit:

- `16877e0ddf19956673f1882ed64a826d1272ca35` fix: fence custody appends and recover post-seal interior audio
- `5bb179e68b53324d9067792d6c9f27d66169f1e4` test: cover crashed recovery producers and rearm partial storage failures
- `0030c62a30c75f3ea71cd2835aec2deca9ea59ea` fix: order late partial recovery after original record publication
- `334b349a64c0d75342e0695244f78c9346736b51` test: model durable append heartbeat in lifecycle reactivation exit
- `864ef7bdb248573d2f0449e9f5b392bf540911d4` test: align custody completion and approved alert contract regressions
- `c8d6df19ad3aaf48b7b8136b8b8f44432de13583` fix: pin recovery policy canonically and keep closed shadow rows inert
- `fb2430f644fcfa530bd450cae9e120135c0b43dd` test: exercise closed shadow rows with existing producer tokens
- `c4dce9e11f922e3915ba1979d1229602805fd4b0` fix: reconcile fresh socket mints after complete record seals
- `a3e347e1b8438f1cafb3ad7e5bcb46ab880cd7ae` fix: subtract earlier WAL units before retaining later overlap

## Files changed by this review correction (22)

- `backend/database/batch_pipeline_record_lease_recovery.py`
- `backend/database/record_audio.py`
- `backend/database/record_custody_append.py`
- `backend/database/record_partial.py`
- `backend/docs/listen_pusher_pipeline.mdx`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-09-token-lease-review-fixes.md`
- `backend/routers/sync.py`
- `backend/testing/lifecycle_properties/test_properties.py`
- `backend/tests/support/lifecycle_state_table.py`
- `backend/tests/support/lifecycle_writer_inventory.py`
- `backend/tests/unit/test_record_custody_append.py`
- `backend/tests/unit/test_record_lease_append.py`
- `backend/tests/unit/test_record_partial.py`
- `backend/tests/unit/test_record_seal_repair.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/tests/unit/test_record_token_lease_deploy.py`
- `backend/tests/unit/test_sync_v2.py`
- `backend/utils/batch_pipeline/CONTRACT.md`
- `backend/utils/batch_pipeline/live_upload.py`
- `backend/utils/batch_pipeline/record_lease_append.py`
- `backend/utils/batch_pipeline/record_seal_cluster_repair.py`
- `backend/utils/sync/record_token_lease.py`

## Follow-up: scope #24953 emulator cleanup

Rebased cleanly onto freshly fetched `origin/main`
`b00957395ff21b5f6758dd0c57680729b6128d9d`, which contains #24953
(`42448d34a441c3f7d64591190b466ab94ce260eb`). The review-fix SHAs above
describe the earlier validation snapshot; the rebase rewrote those commits.

`test_record_seal_nojob_emulator.py` no longer streams/deletes the jobs collection.
Setup and teardown inspect only the nine deterministic synthetic job references
and the late-arrival reference, deleting a reference only when its stored owner
is `synthetic-age-owner`. A real-emulator regression proves cleanup preserves
both a listed document with another owner and an unlisted document with the
synthetic owner. No production code changed in this follow-up.

Validation ran through:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- python3 /Volumes/Ephemeral/scratch/tokenlease-nojob-cleanup-validation.py
# From backend, in a private loopback Firestore emulator:
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_nojob_emulator.py
# From backend:
.venv/bin/python -m pytest -q --tb=short tests/unit/test_record_seal_nojob.py
# From repository root:
make preflight
```

Exact results: **4 emulator tests passed, 44 companion unit tests passed,
56/56 preflight checks passed** (696.46 seconds, exit 0). The launcher removed
GOOGLE_APPLICATION_CREDENTIALS, every CLOUDSDK_* variable and service-account
bindings, and used private HOME/config/cache with anonymous emulator credentials.
The emulator stopped after its suite. GCP tier: none. No push or PR.
Local log: `/Volumes/Ephemeral/scratch/tokenlease-nojob-cleanup-results.log`.
