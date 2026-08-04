# Runbook — reset a user's free-tier transcription (listening) minutes

**Use when:** support needs to inspect or goodwill-reset a user's monthly
transcription minutes after an unexpected burn (e.g. silent open-mic).

**What it touches:** `transcription_seconds` summed from
`users/{uid}/hourly_usage/{YYYY-MM-DD-HH}` for the current calendar month — the
exact surface the cap enforces (`utils/subscription.get_remaining_transcription_seconds`).
This is **not** the fair-use speech-hour system (`/v1/admin/fair-use/...`), which
already has its own reset.

## Tool

`backend/scripts/admin/reset_transcription_usage.py` (run as a module from the
backend dir).

## Credentials

Any account with **prod Firestore write** on the Omi GCP project:

- Service account JSON:
  `GOOGLE_APPLICATION_CREDENTIALS=/path/svc.json`
- Or operator ADC: `gcloud auth application-default login` (with the prod
  project's Firestore Writer / Editor role).

`--email` additionally calls Firebase Auth to resolve the uid; `--uid` needs no
Auth SDK.

## Commands

```bash
cd backend

# 1) Inspect (read-only) — plan / used / limit / remaining / top buckets:
python -m scripts.admin.reset_transcription_usage show --uid <UID>
python -m scripts.admin.reset_transcription_usage show --email user@example.com

# 2) Dry-run reset (default — writes nothing):
python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> \
    --reason "goodwill: silent open-mic burn"

# 3) Apply (zeros current-month transcription_seconds, writes audit record):
python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> \
    --reason "goodwill: silent open-mic burn" --apply --operator "you@"
```

## Safety

- **Dry-run by default.** `reset-month` prints before/after and exits without
  writing unless `--apply` is passed.
- **`--reason` is required** (audited).
- **Before/after totals printed** on every run.
- **Audit trail:** on `--apply`, a doc is written to Firestore
  `admin_audit_log/{auto}` with uid / email / plan / month / reason / operator /
  before / after / docs-touched / timestamp. Dry-runs print the same record as a
  JSON line to stdout (not persisted).
- **No transcript / memory / message data** is read or printed — only the
  numeric `transcription_seconds` counter and doc ids.
- **No new IAM.** Reuses the backend's existing credential loader
  (`database/google_credentials`).

## What is intentionally NOT covered

- **Chat-question quota reset** is deferred. Chat usage lives in
  `users/{uid}/llm_usage/{YYYY-MM-DD}` across several nested/legacy counter
  shapes (`desktop_chat.quota_questions`, `backend_chat.quota_questions`,
  legacy `chat.*.call_count`); zeroing it safely needs integration testing
  against all those shapes, out of scope for this ops tool. Track separately.
- **Fair-use reset** already exists at `POST /v1/admin/fair-use/user/{uid}/reset`
  (`backend/routers/fair_use_admin.py`) — use that for speech-hour state.
- **Automatic goodwill credits / billing policy** — product decision, out of scope.
- **Prod runs** are operator-initiated; this repo's CI only unit-tests the pure
  logic. Never run `--apply` in CI / automated pipelines against real users
  without an operator decision.

## Tests

`backend/tests/unit/test_reset_transcription_usage.py` — pure logic only
(month aggregation, reset-plan shape, audit record, dry-run vs apply). No GCP.
