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

A user's own Firebase token reaches none of these endpoints.

Every call to the context (decrypt) endpoint is logged with the event id, a
hash of the admin key, and the **Firebase uid of the admin who asked**, which
admin.omi.me forwards server-side as `X-Admin-User` after checking it against
`adminData/{uid}`. The key hash alone identifies only the deployment — it is
one shared secret — so it could never say *which* admin read a user's chat.
A read that arrives without the uid header logs as `unattributed`; that is not
an error (the key is still the gate) but it means someone called the backend
directly rather than through the dashboard, which is worth noticing.

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

- **Report cap.** One report is one Firestore document, and Firestore rejects
  any document over 1 MiB outright. Three bounds keep it under that, and
  crossing *any* of them sets `truncated: true` rather than silently showing a
  partial day:
  - `MAX_REPORT_ENTRIES` (500) — entries carried.
  - `RAW_FETCH_LIMIT` (2000) — ledger rows read. Larger than the entry cap
    because one thumbs-down can write several rows that collapse to one entry,
    so judging only on collapsed entries would let a day overrun the fetch and
    still look complete.
  - `MAX_REPORT_DOCUMENT_BYTES` (800 KiB) — serialized size. The entry count
    alone is not a safe bound: 500 entries each carrying a full 21-turn window
    runs to roughly 2 MiB and the write fails, so a heavy feedback day would
    produce *no* report at all. The job measures as it goes and stops.
  When the byte budget cuts a report short, `counts_by_surface`,
  `counts_by_reason` and `total_negative` still describe the **whole** day —
  only the per-event context windows are dropped. The distribution is the part
  you act on; the transcripts are the part you can regenerate or look up.
- **Follow-up cap.** A window carries at most 10 turns before and 10 after. A
  burst of retries past that sets `truncated_after` on the pointer, since the
  window otherwise promises *every* turn inside its five minutes.
- **Unknown session.** A rated message with no `chat_session_id` gets no
  "before" window at all (`resolution_error: preceding_turns_session_unknown`).
  Keeping the time filter without the session filter would return the previous
  ten messages from any conversation and present them as the setup for this
  answer, which is worse than showing nothing.
- **Undecryptable turns.** `utils.encryption.decrypt` returns its *input* when
  decryption fails, so a failed decrypt raises nothing and yields base64
  ciphertext typed as a string. The hydrator compares against the stored value
  and lists such turns in `unavailable` instead of rendering the blob as if it
  were the user's words.
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
