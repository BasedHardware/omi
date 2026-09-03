# Runbook — inspect / reset monthly listening minutes and chat questions

**Use when:** support needs to inspect a user's current-UTC-month quotas, or
goodwill-reset listening minutes (unexpected burn, e.g. silent open-mic) or
chat questions (unexpected chat-quota burn).

**What it touches:**

- **Listening:** `transcription_seconds` summed from
  `users/{uid}/hourly_usage/{YYYY-MM-DD-HH}` for the current calendar month — the
  exact surface the cap enforces
  (`utils/subscription.get_remaining_transcription_seconds`).
- **Chat:** `quota_questions` on `users/{uid}/llm_usage/{YYYY-MM-DD}` for the
  current UTC calendar month — the exact surface
  `database.user_usage.get_monthly_chat_usage` (and
  `utils/subscription.enforce_chat_quota` / `get_chat_quota_snapshot`) reads.

This is **not** the fair-use speech-hour system (`/v1/admin/fair-use/...`), which
already has its own HTTP reset. Plan grants / complimentary entitlements / Stripe
create-or-update are out of scope.

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
Auth SDK. Never derive a UID from PostHog, Firestore email fields, or Stripe.

## Commands

```bash
cd backend

# 1) Inspect (read-only) — plan / status / listening / chat / fair-use pointer:
python -m scripts.admin.reset_transcription_usage show --uid <UID>
python -m scripts.admin.reset_transcription_usage show --email user@example.com

# 2) Dry-run listening reset (default — writes nothing).
#    Refuses unlimited plans (Operator/Architect/Neo listening) unless --force:
python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> \
    --reason "goodwill: silent open-mic burn"

# 3) Apply listening reset (finite cap only, or --force on unlimited):
python -m scripts.admin.reset_transcription_usage reset-month --uid <UID> \
    --reason "goodwill: silent open-mic burn" --apply --operator "you@"

# 4) Dry-run chat-quota reset (default — writes nothing):
python -m scripts.admin.reset_transcription_usage reset-chat-month --uid <UID> \
    --reason "goodwill: chat-quota burn"

# 5) Apply chat-quota reset (zeros current-month quota_questions, writes audit):
python -m scripts.admin.reset_transcription_usage reset-chat-month --uid <UID> \
    --reason "goodwill: chat-quota burn" --apply --operator "you@"
```

`show` after a successful `--apply` of `reset-chat-month` must report chat
questions `0` for that UTC month (`get_monthly_chat_usage`).

## Safety

- **`show` prints `listening throttled: yes/no`.** Unlimited listening is
  never throttled. Do **not** `reset-month` those accounts just because used
  minutes look large. `reset-month` exits 2 on unlimited plans unless
  `--force` (goodwill-zero anyway). Chat is separate: `chat included exhausted`
  is the included-allowance line; paid overage plans are not hard-cut.
- **Dry-run by default.** `reset-month` and `reset-chat-month` print
  before/after and exit without writing unless `--apply` is passed.
- **`--reason` is required** (audited).
- **`--operator` is required with `--apply`** (same flag on both reset commands).
- **Before/after totals printed** on every run. Chat re-reads
  `get_monthly_chat_usage` after apply.
- **Audit trail:** on `--apply`, a doc is written to Firestore
  `admin_audit_log/{auto}`. Listening records before/after seconds; chat records
  `action=reset-chat-quota-month` plus before/after questions, uid / email / plan /
  month / reason / operator / docs-touched / timestamp. Dry-runs print the same
  record as a JSON line to stdout (not persisted). Stdout is PII-sanitized;
  Firestore keeps the full record.
- **No transcript / memory / message data** is read or printed.
- **No new IAM.** Reuses the backend's existing credential loader
  (`database/google_credentials`).
- **Chat reset sets `quota_questions` to 0** (does not delete the key). Deleting
  the key can re-enable legacy fallbacks (`chat.*.call_count`, old
  `desktop_chat_realtime.call_count`). Telemetry (`call_count`, tokens,
  `cost_usd`) is left intact. If the only counted surface is legacy
  `chat.*.call_count`, the tool introduces `backend_chat.quota_questions = 0`
  instead of wiping those counters.
- **Never run `--apply` against real users from CI / automated pipelines.**

## What is intentionally NOT covered

- **Fair-use write** (reset / set-stage) — already
  `POST /v1/admin/fair-use/user/{uid}/reset`
  (`backend/routers/fair_use_admin.py`). `show` may print a one-line
  `fair_use_state/current.stage` if that cheap Firestore field exists; otherwise it
  prints `GET /v1/admin/fair-use/user/{uid}`. Do not wrap the POST from this CLI.
- **Plan grants / complimentary entitlements / Stripe create-or-update.**
- **Deleting `chat_quota_events`** (idempotency log, not the cap).
- **Zeroing `call_count`, tokens, or `cost_usd`** (telemetry, not the cap).
- **Redis proactive / trial-cache.**
- **Account wipe, memory dump, new ADMIN_KEY HTTP routes.**
- **Prod `--apply` against real users** from this repo's CI (dev/emulator/unit
  only).
- **Merge / deploy.**

## Tests

`backend/tests/unit/test_reset_transcription_usage.py` — pure logic only
(month aggregation, listening reset-plan, chat nested/dotted/`plan_usage`
shapes, dry-run vs apply shape, audit record including
`reset-chat-quota-month`, “do not count `desktop_chat.call_count` as quota”).
No GCP.
