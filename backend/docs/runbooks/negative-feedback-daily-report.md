# Daily negative-feedback report

Every thumbs-down the product collects, for one UTC day, with the conversation
around it. Read it at **<https://admin.omi.me/dashboard/feedback>**.

## What it answers

For each thumbs-down: what the user asked, what Omi answered, what the user did
next within five minutes, and — where the client asked — why they rated it down.
The point is that a rating alone ("14 thumbs-down yesterday") tells you nothing
actionable; the turn before it and the retry after it usually tell you
everything.

## Where the data lives

| Collection | Holds | Written by |
| --- | --- | --- |
| `feedback_events` | One append-only row per rating action, all surfaces | `utils/feedback.py`, from every rating endpoint |
| `feedback_reports/{YYYY-MM-DD}` | One day's report: counts + **pointers** | `jobs/feedback_daily_report.py` |

Neither collection contains conversation text. That is deliberate, and it is
the reason the report is a two-step read rather than one document.

## Why the report stores pointers instead of transcripts

Chat message text is encrypted at rest with a key derived per user from the
backend's `ENCRYPTION_SECRET` (`utils/encryption.derive_key`), and `enhanced` is
the default protection level, so this is the normal case rather than an opt-in
minority. Materializing readable transcripts into a report collection would
create a second, permanently unencrypted copy of user conversations, readable by
anything holding the Firestore service account.

So the nightly job reads only the plaintext *metadata* on a message document —
id, sender, `created_at`, `chat_session_id` — and writes those. It never touches
`text`. When a reviewer expands an entry on admin.omi.me, the backend decrypts
that one window for that one response and returns it without storing it.

## Access control

Three gates, all of which must pass:

1. **admin.omi.me** — the browser signs in with Firebase and the route handler
   requires a `adminData/{uid}` document (`web/admin/lib/auth.ts`).
2. **`X-Admin-Key`** — the Next.js route adds the backend `ADMIN_KEY`
   server-side. It lives only in Cloud Run runtime secrets and never reaches the
   browser.
3. **GCP** — reading the raw collections directly requires Firestore access in
   the project.

A user's own Firebase token reaches none of these endpoints. Every call to the
context (decrypt) endpoint is logged with the event id and a hash of the admin
key, so reads of user conversations are attributable after the fact.

## The window

- **Before:** turns in the same `chat_session_id` up to the rated one, newest 10
  kept (`truncated_before` marks a cut).
- **After:** every turn within **5 minutes**, *regardless of session* — a user
  who gives up and opens a fresh chat is the follow-up most worth seeing.

Constants: `FOLLOW_UP_WINDOW_SECONDS`, `MAX_PRECEDING_TURNS`,
`MAX_FOLLOW_UP_TURNS` in `utils/feedback_context.py`.

## Surfaces covered

| Surface | Rating path | Reason captured? |
| --- | --- | --- |
| `chat_text` (mobile) | `POST /v1/users/analytics/chat_message`, `PATCH /v2/messages/{id}/rating` | Yes |
| `chat_text` (macOS main window) | `PATCH /v2/desktop/messages/{id}/rating` | Yes — picker shipped with this change |
| `chat_voice` (macOS floating bar) | same, `surface=voice` | **No** — the hover overlay has no room for the chip row; needs its own design pass |
| `chat_notification` (proactive cards) | same, `surface=notification` | **No** — the picker is only on answer bubbles |
| `conversation_summary` | `POST /v1/users/analytics/memory_summary` | No — that endpoint takes a score only |
| `memory` | `POST /v3/memories/{id}/review` | No — keep/discard is binary |

A thumbs-down with no reason is counted as **`not_captured`**, never as "no
reason given". Those are different facts and the report keeps them apart.

`chat_notification` is split out for the same reason PR #12626 excluded these
from the response-quality ratio: rating a proactive focus/insight/task card
judges the notification, not an answer Omi gave. Reading them as chat failures
would blame the wrong system.

## Scheduling

The job runs off a Cloud Scheduler job hitting an admin endpoint, the same shape
as the admin dashboard's `precompute` cron. It is **not** defined in this
repository; create it once per environment:

```bash
gcloud scheduler jobs create http feedback-daily-report \
  --schedule="30 1 * * *" \
  --time-zone="Etc/UTC" \
  --uri="https://<backend-host>/v1/admin/feedback/reports/generate-yesterday" \
  --http-method=POST \
  --headers="X-Admin-Key=<ADMIN_KEY>" \
  --attempt-deadline=1800s
```

01:30 UTC leaves an hour and a half of slack after the day closes, so a late
rating write cannot land after the report has already been built.

## Backfill and recovery

A day whose run failed can be rebuilt from the ledger at any time — the events
are append-only and are not deleted with the report:

```bash
curl -X POST -H "X-Admin-Key: $ADMIN_KEY" \
  "https://<backend-host>/v1/admin/feedback/reports/2026-09-01/generate"
```

The **Regenerate** button on the dashboard does exactly this for the selected
date.

## Known limits

- **Report cap.** One report is one Firestore document (1 MiB), so it holds at
  most `MAX_REPORT_ENTRIES` (500) entries, read from at most `RAW_FETCH_LIMIT`
  (2000) ledger rows. Hitting *either* bound sets `truncated: true` rather than
  silently showing a partial day. The two limits differ because one thumbs-down
  can write several ledger rows that collapse to one entry, so judging the cap
  only on collapsed entries would let a day overrun the fetch and still look
  complete.
- **Deleted messages.** A conversation deleted between the nightly run and a
  reviewer's read comes back in `unavailable` rather than as a gap.
- **No history before deploy.** The ledger starts empty; the first report covers
  only ratings recorded after this ships. The legacy `analytics` rows
  (`type: 'chat_message'`) are untouched and still feed the existing PostHog
  ratio charts.
- **One entry per rated message.** The macOS client sends the rating on tap and
  again when a reason is picked, so the ledger holds two rows; the report keeps
  the later one. Ledger row counts and report entry counts are therefore not
  the same number.
