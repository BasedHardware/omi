# Support transcription credit after the plan allowance

**What changed.** Transcription admission (`utils.subscription.resolve_transcription_allowance`) can now answer
`managed` with reason `support_credit` for a user whose finite plan allowance is spent, when support has granted
them credit. The credit is a map at `users/{uid}.support_transcription_credit`, keyed by the `support_actions`
id that wrote it. Its only writer is the support operator CLI (`omi-support-ops transcription-credit grant|revoke`).
It funds live and batch alike, and expires (default 30 days, at most 90).

- Only exhausted users read the credit: one users-root point read, plus one monthly total per earlier month while
  a grant spans a reset. Users within their allowance read nothing new.
- The balance is derived from the existing monthly usage totals; nothing is written at usage time. Each grant
  records the month's usage at grant time, so earlier usage never spends it, and a month reset never re-grants
  spent seconds. Where a grant expired mid-month, overage is charged to the grant still usable, so the balance can
  understate a credit but never overstate it.
- The batch hold controller's entitlement generation includes the credit, so a grant re-offers the owner's
  cap-held units at the next hold check (about 5 minutes).
- A credit read failure or a malformed map is no credit (today's `plan_allowance_exhausted` stands). A valid credit
  whose past-month usage cannot be read is the transient `allowance_unavailable`.

**Why.** David, 2026-11-27 (SCA-5263): support needs a guarded, audited way to process a customer's parked
backlog instead of waiting for the monthly reset.

**Flag.** `SUPPORT_TRANSCRIPTION_CREDIT_ENABLED`, on unless set to false, 0, off or no. Off ignores stored credits
without erasing them, and removes the credit from the hold generation; turning it back on re-offers once.

**Rollback.** Set the switch off, or revoke the grant with the CLI. Work already admitted still completes.

**Runbook.** `backend/docs/runbooks/support-operator-cli.md`, "Transcription credit".
