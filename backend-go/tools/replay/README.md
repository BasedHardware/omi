# Finalization replay oracle

Replay the same stored recording state through Python admission and its persisted finalizer
and through the Go conformance worker in `cmd/jobd`. The runner seeds identical snapshots
in two private projects on one Firestore emulator. It runs the Go queue against a fresh
database on local Postgres 16. Python's native queue and leases live in Firestore. Both
use deterministic responses at the notes and memory provider boundaries. The Python
webhook fanout uses its real payload builder and an in-process transport. The Go shim
records the conformance port's webhook requests and persists its memory and vector
effects in Firestore.

The runner compares disposition, every stored conversation field, changed derived
documents, and webhook deliveries. Object comparison distinguishes missing fields from
nulls. The report includes stable JSON Pointer paths and a reason for each allowed
difference. The allowlist covers generated queue IDs, delivery keys and the conversation's
write clock when both values are present. It does not absorb absent fields, extra
documents or payload changes. The two Python queue bookkeeping collections are outside
the derived-document comparison. Their public effect is represented by the finalization
disposition. Webhook deliveries are sorted by destination with ordering preserved within
each destination.

## Run

From `backend-go/`, with the backend lock installed via
`../backend/scripts/sync-python-deps.sh`, Postgres 16, Java 21 and firebase-tools 15:

```sh
./tools/replay/test.sh
```

The test starts local emulators with the same wrappers as `make check`. It accepts
`REPLAY_PYTHON` with an absolute path to a different backend interpreter.
The command is suitable for a CI runner with the locked Python environment installed.

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
results), `repeat` (duplicate admission), and `own_key` (seeded subscription mode).
Add consented captures as private corpus files with stored transcript fields already
re-encrypted under a replay-only key. Pass the owned mode-0600 key file as
`-test-key-file`. Both workers use that key. The oracle does not fetch recordings or
read production keys.

## Checks and current coverage

| Rule | Proof |
| --- | --- |
| Nested fields, arrays, numeric values, missing fields and escaped paths compare deterministically | `TestCompareReportsNestedDiffsAndKeepsPresence` |
| Missing evidence or driver errors cannot yield a pass | `TestCompareRejectsInvalidEvidence`, `TestCompareCountsExecutionErrors` |
| Ten completed, failed, discarded and missing-row admissions across both paths produce zero unexplained differences | `test.sh` with `corpus/parity.json` |
| Active workers actually persist notes, reach the memory and vector sinks and send both webhooks. Standard and encrypted compressed transcripts reach completion, and empty input exposes disposition drift | `test.sh` with `corpus/conformance-gaps.json` |

The active corpus is a detection test for the interim conformance port. It intentionally
exits 1. Current differences include Go's conformance payload, Python-only Home and
episode projection fields, and empty-input disposition. Updating the candidate to lane
6 requires swapping the conformance launcher and wire shim for the real worker.
