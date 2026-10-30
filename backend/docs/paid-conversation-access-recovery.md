# Paid conversation access recovery (#20590)

Older conversations can retain `is_locked` after a subscription upgrade or a
transient historical allowance failure. Stats and a record's stored lock are
separate projections; a client-side Unlimited label is not authorization.

`utils/conversations/paid_lock_recovery.py` owns read-time restoration. It reads
the real active paid subscription with a fresh subscription-cache scope, then
uses the existing ordinary transcription allowance with BYOK disabled. Only
ordinary available plan/budget reasons admit recovery. Free, inactive, exhausted,
reviewer/BYOK overrides and unresolved authority cannot grant access. Unknown
allowance or failed persistence yields retryable 503, rather than a purchase
denial or a false successful unlock.

Detail, list, exact-reference, speaker browsing and keyword search use that same
boundary. Speaker browsing admits recoverable matches before lock filtering,
using one request-scoped authority check; only the selected page is persisted,
not skipped pages or lookahead. Me and named-person HTTP regressions cover this
ordering without requiring a prior list/detail read. The slim list projection
remains enabled. Keyword search retains owner-scoped locked
index candidates internally; it rehydrates their own Firestore records and
verifies paid access before restoring and returning any locked match. Unlocked
search results do not gain an entitlement dependency. Remaining locks cannot
contribute to pagination metadata. Other search
callers keep the default locked-hit filter. A sync redirect repairs the survivor
ID. A stored `processing_deferred` backlog still requires its explicit processing
choice and is excluded from restoration.

The database update owner changes only access metadata, preserving transcript,
audio, summaries and existing people/search invalidation. The in-memory lock is
cleared only after an acknowledged durable update; partial failures remain
retryable. Recovery itself schedules no STT/AI work, billing, account sweep,
subscription mutation or client reset. Successful already-unlocked reads do not
resolve entitlement again. Work is limited to the existing response page.

The original PR's subscription-refresh sweep called a default-off monthly reset
worker and could never restore access by default. It is removed; current main's
funded-backlog subscription response is preserved. The separately documented
[monthly reset recovery](locked-content-reset-recovery.md) stays default-off.
Refreshing the conversation list or opening a saved reference restores a paid
owner's historical access without that flag or an Android binary change.

Implementation and rollout checklist:

- [x] Real HTTP list/detail/new-client lifetime and keyword search regressions.
- [x] Browse-first Me/named-person recovery, denial, retry, deferred backlog,
  page-only writes and truncation coverage from the separate speaker fix.
- [x] Free/inactive/exhausted/BYOK denial, unresolved allowance retry, write
  failure/retry, redirect identity, and explicit backlog choice coverage.
- [x] Original stored content preserved; no automatic processing or charge.
- [x] Focused backend suites, type checks and the 34-check PR preflight.
  The complete selector-owned CI contract and remote CI are recorded on the PR.
- [ ] Merge, then deploy the backend API; no mobile release or flag activation
  is required for this server-side repair.
- [ ] Privately confirm Thomas's paid account/upgrade date and affected record,
  then verify that Android refresh, reopen and restart retain access. Keep
  #20590 open until this deployed account check succeeds. A screenshot alone
  cannot establish the actual billed entitlement or that recovery has occurred.
