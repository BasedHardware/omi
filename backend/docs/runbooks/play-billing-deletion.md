# Play Billing: stuck account deletion

Deleting an account first stops Google Play from charging it (`utils/play_publisher.py`), and the deletion is never
completed while Google can still charge. Two states can stick. Both retry on their own; these filters find them.

The backend logs in text mode (`backend/main.py`, `default_format='text'`): WARNING and above go to stderr as
`<LEVEL> <logger>: <message>`, which Cloud Logging stores as severity ERROR (a `logger.critical` line too), with the
text in `textPayload`. The `jsonPayload.message` half of each filter covers a later switch to JSON logging.

## 1. Grace-mode cancel keeps failing (admission)

A grace-period deletion cancels at admission; the reconciler retries every cycle and never dispatches the wipe
until the cancel succeeds, even past the due date.

```
severity>=ERROR AND (textPayload:"delete_account grace immediate-action retry failed for" OR jsonPayload.message:"delete_account grace immediate-action retry failed for")
```

Each line carries `attempts=`, `age_seconds=` and `overdue=`; page on `overdue=True` (add
`AND (textPayload:"overdue=True" OR jsonPayload.message:"overdue=True")`). The deletion marker holds the same state
(`grace_actions_failed_attempts`, `grace_actions_last_failed_at`, `grace_actions_overdue`), and PostHog gets
`Account Deletion Wipe Failed` with `failed_operations=['grace_immediate_actions']`.

## 2. Wipe fails on Play (billing step or Play-records step)

The wipe stops either at its billing step (Google cannot confirm the cancel: billing may continue) or at
`play_billing_records` (a purchase is chargeable again, was not confirmed in this run, or Google cannot be read:
Auth and derived data are already gone, Firestore user data is not). It retries with backoff, capped at 1 hour.

```
severity>=ERROR AND (textPayload:"delete_account background wipe failed for" OR jsonPayload.message:"delete_account background wipe failed for") AND (textPayload:"Google Play cancel not confirmed" OR textPayload:"has no confirmed deletion cancel" OR jsonPayload.message:"Google Play cancel not confirmed" OR jsonPayload.message:"has no confirmed deletion cancel")
```

The error names the HTTP status and a masked prefix of the purchase's Firestore key (`a1b***5f6`: the key is the
SHA-256 of the token, never the token); match it against `play_subscription_purchases` document ids for the uid.
PostHog: `Account Deletion Wipe Failed` with `failed_operations` containing `billing_subscription` or
`play_billing_records`.

## What to do

1. `status 403` (or 401): the runtime service account lost Play Console access (View financial data / Manage
   orders). Restore it; the next retry clears every stuck deletion.
2. `status 5xx` or `unavailable`: a Google outage or a purchase that is chargeable again (resubscribed in Play).
   Wait for the next retries; if one key stays stuck more than a day, look the purchase up in Play Console
   (Order management) by the user's order and cancel it there, then let the wipe retry.
3. `has no confirmed deletion cancel`: a purchase appeared after the billing step; the next retry cancels it.
4. Never delete `play_subscription_purchases` documents by hand while Google can still charge them: that is how
   a deleted account keeps being billed.
