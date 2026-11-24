# Finalization replay oracle

Replay the same stored recording state through Python admission and its persisted finalizer
and through the current Go conformance worker in `cmd/jobd`. The runner seeds identical snapshots
in two private projects on one Firestore emulator. It runs the Go queue against a fresh
database on local Postgres 16. Python's native queue and leases live in Firestore. Both
use deterministic provider responses. Python runs its production notes shaping, canonical
memory extraction and persistence, app summaries, folder assignment, task and goal writes,
and both webhook builders. A loopback HTTP server serves the model responses and receives
webhooks. The recorder also captures writes at the vector vendor SDK boundary. The Go shim
adapts the same notes and memory responses to the conformance protocol and records the Go
worker's webhook, vector and memory operations.

The runner compares disposition, every stored conversation field, changed derived
documents, vendor effects, provider call counts by lane, and webhook deliveries by destination and delivery order.
Comparison covers persistent and outbound effects. Redis cache and suppression keys, mixed-version
ownership handback and rollback durability are outside this replay contract; the shadow plan covers
those behaviors.
Both observations must supply JSON objects for derived documents and vendor effects. Empty objects are valid.
Object comparison distinguishes missing fields from nulls. The report uses JSON Pointer
paths and gives a reason for each allowed difference. Generated job and fanout IDs
must agree with the corresponding side's admission and stored binding. The
fanout comparison pairs the Python queue document with the Go conversation. Changed write
timestamps must land inside the corresponding side's execution window. Python-only
effects such as canonical memory documents, app results, folders, tasks, goals, and
the developer-created webhook appear as `unported` when missing in Go. They still
count as unexplained differences. Queue bookkeeping collections are excluded from the
derived-document diff, with the finalization disposition and queue binding checked directly.

The approved timestamp, goal-event and Home-token rules for the 438-difference
ordinary-sync report are recorded in [`comparison-rules.md`](comparison-rules.md).
Each rule checks side-local evidence before explaining a difference. The
`finalization_job_id` difference remains unexplained pending the required reader and
queue-binding evidence. No rule treats null and absent as equivalent; Go must match
Python's stored writes.

## Run

From `backend-go/`, with the backend lock installed via
`../backend/scripts/sync-python-deps.sh`, Postgres 16, Java 21 and firebase-tools 15:

```sh
../backend/.venv/bin/python -c "import tiktoken; tiktoken.encoding_for_model('text-embedding-3-large')"
./tools/replay/test.sh
```

The test starts local emulators with the same wrappers as `make check`. It accepts
`REPLAY_PYTHON` with an absolute path to a different backend interpreter.
The first command primes the tokenizer dependency cache before network isolation. The
existing Backend Go Checks workflow installs locked Python dependencies, primes the cache,
and runs the replay test against its Postgres 16 service and Firestore emulator.

### Workerd diagnostic (not the gate)

The gate remains `test.sh` and its `cmd/jobd` driver. To measure the same pinned 41-case
synthetic corpus against a draft that contains the ordinary-sync replay seam, run from the
repo root with local Postgres 16, Java 21 and Firebase CLI available:

```sh
make oracle-diag WORKERD_REF=<full-workerd-commit-sha> \
  ORACLE_DIAG_OUTPUT=../ordinary-sync-report.json
```

The default linked-checkout root is `/Volumes/scratch/worktrees`; set `OMI_WORKTREES`
when the machine uses another managed Git-worktree root.

This target builds the opt-in test binary from `WORKERD_REF`, runs the separate
`ordinary_sync_diag.py` adapter, and compares its row-level observations with the same
oracle comparator. The value-free report records each difference's family, path, kind,
label, and approved reason. Labels are `go_gap`, `python_bug:<issue>`, or
`by_design:<rule>`; the by-design suffix is the comparator's approved reason. Rows without
a reviewed label have `label: null` and count as unlabelled. It includes totals by label
and family. Invalid Home token evidence includes a per-slot `failure_reason`, without token
values. The SCA-3874 case runs Python through the fake Cloud Tasks queue and the real
enrichment route to its durable age park. The reporter labels the parked-versus-dead-letter
status difference as SCA-4178 after checking custody and retry evidence. Cost includes the
full Python retry lifecycle. Pass-3 Go-gap patterns from SCA-4012 are applied from
`approved-go-gaps-sca-4012.csv` to currently unlabelled rows. The report's unexplained gate count
is `go_gap + unlabelled`; Python-bug exception rows are reported separately. Protected payload,
clock, ID, and token checks are listed in `comparison-rules.md`.
Family attribution uses this precedence: goals; apps and webhooks; memory source and
metering; digest, minimum and relevance; other. The report exposes remaining unlabelled groups
separately from rows already classified as Go gaps.

The seam admits each fixture as one `sync_update` over a stored completed row. It does not
exercise per-case trigger behavior, repeat-admission, final-attempt handling,
`delete_before_worker_read`, or `erase_after`; those are listed in the report and remain
uncovered until the real driver swap. Missing rows are materialized from their synthetic
recording for this diagnostic. The target does not change `test.sh` or the cohort gate.

To examine the active corpus interactively:

```sh
work=$(mktemp -d)
go build -o "$work/jobd" ./cmd/jobd
go build -o "$work/replay" ./tools/replay
./scripts/with-postgres.sh ./scripts/with-firestore.sh \
  "$work/replay" -jobd "$work/jobd" -commit "$(git rev-parse HEAD)" \
  -corpus tools/replay/corpus/conformance-gaps.json \
  -output "$work/report.json" -include-values
```

The tool requires a 40-character `-commit` SHA and records it beside the unexplained-
difference count. Its JSON report has a cost-table row for each case and both paths:
estimated LLM prompt/completion tokens, embedding input tokens, and Firestore request and
document-operation counts. Token counts use `cl100k_base` over content text and exclude API
framing; they are estimates, not provider-billed usage. Firestore counts cover the product
run; corpus seeding, snapshots, observation and cleanup are excluded. The tool also prints
aggregate totals as a convenience.

Until the driver switches to the lane 6 worker, the Go column and aggregate Go totals are
measurements for the `cmd/jobd` conformance driver. Do not use the Go-versus-Python cost
comparison as a gate on this interim run; the Go ≤ Python criterion applies to the lane 6
worker replay.

The Firestore meter counts direct document-read attempts before dispatch, including failed
RPCs. Stream request counts are recorded when the RPC is started, while document counts cover
only results consumed by the replay; a partially consumed stream can have fetched and billed
additional results, so streamed document counts are a lower bound.

The tool exits **0** for parity, **1** for unexplained differences, and **2** for a setup,
execution, or report error. It creates a new mode-0600 JSON file and refuses to overwrite a
report. By default it reports paths, refusals and counts. The CLI rejects report locations inside Git worktrees.
`-include-values` is available only for the reviewed synthetic fixtures pinned by digest.
The CLI rejects changed or unreviewed in-repo corpora. Paths can include fixture document
IDs even when values are omitted. Pass `-backend /absolute/path/to/omi/backend` when running
from outside the checkout with an external corpus.

The replay launches the conformance binary on an OS-assigned loopback port and reads
the bound address from the process, avoiding a separate port probe.
The replay driver validates both database endpoints as loopback and clears inherited
credentials, vendor endpoints and proxy settings before launching either path. It
cleans up both emulator projects and drops its disposable Postgres database.

## Add cases

Add a unique lowercase slug and recording to a version-1 corpus. A recording includes
`duration_s` and timed `segments`. Each segment needs `text` and can override the
generated `id`, `start`, `end`, and `is_user`. Replay starts at the persisted
transcript boundary. It does not decode audio, rerun STT or enable external providers.

```json
{
  "version": 1,
  "cases": [{
    "name": "team-agenda",
    "recording": {"duration_s": 32, "segments": [{"text": "Review the synthetic agenda."}]},
    "apps": ["sample-app"],
    "notes": {"title": "Sample", "overview": "Review the agenda."}
  }]
}
```

Use `document` to override stored fields or set it to null to test an absent row.
`{"$timestamp":"2026-01-02T12:00:00Z"}` and `{"$bytes":"<base64>"}` preserve
Firestore timestamps and bytes. `uid` and `conversation_id` override synthetic
identifiers. UIDs must be unique within a corpus. Use separate corpus files to replay multiple recordings for the same owner. Other case controls are `trigger`,
`end_reason`, `revision` (the Go endpoint's requested revision), `min_words`
(the deterministic notes fixture's discard floor), `memories` (scripted extraction
results), `repeat` (duplicate admission), and `own_key` (seeded subscription mode and
fixture live-session key). Use `responses` to supply recorded, synthetic gateway response
bodies keyed by model lane (for example `conv-structure` or `memory-l1`). The conformance
adapter projects title and overview from notes and text from memory candidates. The report
can show response paths and effects that only Python currently supports.
Both vector receivers record the common ordered conversation-write identities. They also
retain their different transport payloads separately as drift.
Set `final_attempt` and name an `unavailable_app` from `apps` to exercise the
terminal delivery path with a synthetic HTTP 503.
Review new in-repo fixtures as synthetic, including decoded encrypted fixture contents,
before updating their SHA-256 pins in `paths.go`. The 51-case active floor and each case's
contract-rule mapping are in `case-map.json`. It names every F01–F38 rule the current oracle
can drive and those it cannot. `corpus/held-out.json` contains four synthetic cases excluded
from CI replay until the worker exposes the needed seams.

The optional owner-corpus hook accepts 15–25 conversations (about 20) supplied by the lead,
re-encrypted under a replay test key for unique synthetic `replay-*` UIDs. Keep
`corpus.json` and the mode-0600 `-test-key-file` outside Git. The hook is enabled only on
`m5-mbp`, rejects CI, and writes reports without observations. Example after the lead supplies
both files:

The m5 hostname and CI checks are operational guards against accidental use, not a security
boundary. A process with access to the host and files can bypass them; the hook validates each
enhanced transcript envelope with the external replay test key before opening the oracle.

CI fixture content is read and then checked against its reviewed digest before it is parsed or used.

```sh
work=$(mktemp -d)
go build -o "$work/jobd" ./cmd/jobd
go build -o "$work/replay" ./tools/replay
./scripts/with-postgres.sh ./scripts/with-firestore.sh \
  "$work/replay" -owner-corpus-dir "$OWNER_CORPUS_DIR" -test-key-file "$REPLAY_TEST_KEY" \
  -backend "$PWD/../backend" -jobd "$work/jobd" -output "$work/owner-report.json" \
  -commit "$(git rev-parse HEAD)"
```

The hook never loads owner material in CI; no owner corpus is checked in. Adding or
replacing cases in the supplied external `corpus.json` needs no code change. The oracle does
not fetch conversations or read production keys.

## Checks and current coverage

| Rule | Proof |
| --- | --- |
| Nested fields, arrays, numeric values, missing fields and escaped paths compare deterministically | `TestCompareReportsNestedDiffsAndKeepsPresence` |
| Object, array, scalar and null mismatches produce a report | `TestCompareDifferencesWithIncompatibleJSONShapes` |
| Go-only fanout and ownership receipts require side-local evidence; conversation and nested write clocks are checked in their own windows | `TestGoOnlyReceiptsRequireBoundGoEvidenceAndNoPythonCopies`, `TestApprovedConversationAndNestedWriteClocksAreChecked` |
| Each approved derived timestamp retains its Firestore or RFC3339 type, is inside its own replay window, and meets its fixture day bucket | `TestApprovedTimestampRulesRequireSideLocalTypeAndWindow` |
| Goal event IDs bind to their paths, parent goals and progress sequence before event semantics are compared | `TestGoalEventIdentityIsBoundBeforeSemanticComparison` |
| Every approved Home token is UUIDv4 hex, fresh, unique in its side's run, and bound to the same-side dependent record | `TestEachHomeTokenRequiresUUIDv4AndItsSameSideLink`, `TestHomeTokensRejectSeedCollisionsAndRunWideDuplicates` |
| Missing evidence or driver errors cannot yield a pass | `TestCompareRejectsInvalidEvidence`, `TestCompareCountsExecutionErrors` |
| Ten completed, failed, discarded and missing-row admissions across both paths produce zero unexplained differences | `test.sh` with `corpus/admission-parity.json` |
| Forty-one active-worker cases persist notes, reach the memory and vector sinks, deliver webhooks, resume seeded own-key jobs and cover the mapped F01/F02/F04/F08/F09/F14/F17/F32 surfaces; Python also runs its canonical memory, app, task, folder, goal and developer-webhook code | `test.sh` with `corpus/conformance-gaps.json` and `case-map.json` |
| Deferred live and batch receipts expose their stored `sync_content_revision` through REST and MCP list, search and detail; the second segment is returned after the initial cached miss and repeated reads request no enrichment promotion. Locked/erased detail reads retain typed HTTP refusals; unreadable ciphertext is covered by the dead-letter case. A non-deferred GUI detail open is the positive control. | `test_deferred_live_and_batch_receipt_reads_return_latest_revision_without_enrichment` in `backend/testing/e2e/test_retrieval_search.py` and `unreadable-ciphertext-dead-letters` |

The ten-case admission corpus is a zero-difference gate. The 41-case active-finalizer corpus
is an interim measurement against `cmd/jobd`; its unexplained-difference count is expected to
be nonzero. The gate records that count per commit, with no expected-drift signature pin,
and preserves reasons on allowlisted differences. CI verifies the count against the observed
unexplained paths and requires zero execution errors. This is the lane 6 worklist, not the
final cohort gate. `test.sh` also mutates the recorded fence outcome and duplicates a paid
model call, then verifies each mutation is rejected. The workerd diagnostic target above is
for draft-to-draft measurement only. After the lane 6 handler lands and the driver swap is
approved, the cohort gate must run the full corpus and both mutations against the worker.

The oracle does not cover Redis cache or suppression keys, mixed-version ownership handback,
or rollback durability; the shadow plan covers these behaviors. Separate cases assert that
post-finalization erase removes the Go owner document and queue rows, and that malformed
enhanced ciphertext produces a typed `transcript_unreadable` dead-letter without reaching
note generation.
