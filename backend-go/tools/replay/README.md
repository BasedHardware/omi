# Finalization replay oracle

Replay the same stored recording state through Python admission and its persisted finalizer
and through the Go conformance worker in `cmd/jobd`. The runner seeds identical snapshots
in two private projects on one Firestore emulator. It runs the Go queue against a fresh
database on local Postgres 16. Python's native queue and leases live in Firestore. Both
use deterministic provider responses. Python runs its production notes shaping, canonical
memory extraction and persistence, app summaries, folder assignment, task and goal writes,
and both webhook builders. A loopback HTTP server serves the model responses and receives
webhooks. The recorder also captures writes at the vector vendor SDK boundary. The Go shim
adapts the same notes and memory responses to the conformance protocol and records the Go
worker's webhook, vector and memory operations.

The runner compares disposition, every stored conversation field, changed derived
documents, vendor effects, and webhook deliveries by destination and delivery order.
Object comparison distinguishes missing fields from nulls. The report uses JSON Pointer
paths and gives a reason for each allowed difference. Generated job and fanout IDs
must agree with the corresponding side's admission and stored binding. Changed write
timestamps must land inside the corresponding side's execution window. Python-only
effects such as canonical memory documents, app results, folders, tasks, goals, and
the developer-created webhook appear as `unported` when missing in Go. They still
count as unexplained differences. Queue bookkeeping collections are excluded from the
derived-document diff, with the finalization disposition and queue binding checked directly.

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

To examine the active corpus interactively:

```sh
work=$(mktemp -d)
go build -o "$work/jobd" ./cmd/jobd
go build -o "$work/replay" ./tools/replay
./scripts/with-postgres.sh ./scripts/with-firestore.sh \
  "$work/replay" -jobd "$work/jobd" -corpus tools/replay/corpus/conformance-gaps.json \
  -output "$work/report.json" -include-values
```

The tool prints one summary line and exits **0** for parity, **1** for unexplained
differences, and **2** for a setup, execution, or report error. It creates a new
mode-0600 JSON file and refuses to overwrite a report. By default it reports paths,
refusals and counts. Use `-include-values` to include the original observations when
working with synthetic data. Keep private corpora and reports outside the repository.
Paths can include fixture document IDs even when values are omitted.

Use an isolated developer or CI machine for this command. The conformance binary
binds an ephemeral port on all interfaces and is intended only for local test use.
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
Add consented captures as private corpus files with stored transcript fields already
re-encrypted under a replay-only key. Pass the owned mode-0600 key file as
`-test-key-file`. Both workers use that key. The oracle does not fetch recordings or
read production keys.

## Checks and current coverage

| Rule | Proof |
| --- | --- |
| Nested fields, arrays, numeric values, missing fields and escaped paths compare deterministically | `TestCompareReportsNestedDiffsAndKeepsPresence` |
| Object, array, scalar and null mismatches produce a report | `TestCompareDifferencesWithIncompatibleJSONShapes` |
| Job IDs and fanout keys must match admission, and generated timestamps must be inside the replay window | `TestCompareOnlyExcusesVerifiedBindingsAndClocks` |
| Missing evidence or driver errors cannot yield a pass | `TestCompareRejectsInvalidEvidence`, `TestCompareCountsExecutionErrors` |
| Ten completed, failed, discarded and missing-row admissions across both paths produce zero unexplained differences | `test.sh` with `corpus/parity.json` |
| Active workers persist notes, reach the memory and vector sinks, deliver webhooks and resume a seeded own-key job. Python also runs its canonical memory, app, task, folder, goal and developer-webhook code. Compressed and enhanced transcripts complete, and empty input exposes disposition drift | `test.sh` with `corpus/conformance-gaps.json` |

The active corpus is a detection test for the interim conformance port. It intentionally
exits 1. Current differences include Go's conformance payload, Python-only Home and
episode projection fields, and empty-input disposition. Updating the candidate to lane
6 requires swapping the conformance launcher and wire shim for the real worker.
