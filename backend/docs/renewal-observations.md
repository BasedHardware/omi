# Renewal outcome observations

Observation-only backend instrumentation for the churn program; no notification,
entitlement, Stripe-setting or historical-data changes. Source does not prove serving.

After signature validation and return of the owning handler (including retryable skips), the Stripe webhook records a minimal immutable fact for
subscription-cycle invoice finalization, failed payment, paid/payment_succeeded,
void and uncollectible events. It also records provider subscription status/cancel
transitions with a hashed latest-invoice link. It never reads Stripe or user docs.
`BILLING_RENEWAL_OBSERVATIONS_ENABLED=false` disables projection and observation IO;
code defaults on (ops kill switch), with no runtime/config deployment in this PR.
A default-off experiment ramp is not appropriate for observation-only instrumentation.

`billing_renewal_observations` documents contain hashes of invoice/subscription keys,
allowlisted enums, provider livemode, attempt_count/attempted, positive-amount flag, provider
invoice periods, timestamps and expiry. No UID, customer, contact, card, price ID,
line content, full payload or raw provider identifier is persisted. Hashes are
join keys inside trusted analytics, never Prometheus labels or public output.
Creator-app metadata is excluded. Unknown/mixed/truncated price coverage remains
unknown and must be reported separately from recognized consumer prices.

Invoice key + attempt_count + normalized outcome is the create-only semantic key.
Paid aliases and webhook redelivery dedupe; a later failed retry is separate, and
an out-of-order failure cannot overwrite a paid observation. Read outcomes as a
set of provider facts ordered by provider event time, not by arrival or doc ID.
Finalized/void/uncollectible and out-of-band paid invoices are not payment attempts.
Count attempted positive-due invoices separately from attempt outcomes. Cohort invoices by the first observed finalized/attempt provider timestamp and disclose source-start left truncation; invoice period fields are raw provider periods, not service periods or anniversary dates. A raw subscription snapshot is not effective payer churn;
replacement and paid-through rules remain the churn producer's authority.
First versus later renewal ordinal is explicitly unknown without more history.

Persistence uses a create RPC with retry disabled and one-second SDK deadline,
offloaded to the DB executor with a 1.25-second await bound. Production uses the response BackgroundTasks after the owning handler returns, so observation does not delay its response; direct Python callers without a response container await the bounded observer. Observation is first in the response task list so a later notification/policy exception cannot suppress it; it can delay other background work by up to the observer bound. Process exit, response-serialization failure or disconnect before response can lose observations. Duplicate creation is
expected. Failures record the shared fallback signal and type-only logs; the owning
webhook response body/effects are unchanged. Observation runs after entitlement decisions, so observation IO/logging cannot change their decision clock. A raising owning handler records nothing on that attempt; retryable-skip returns still record provider facts (not effective entitlement changes); Stripe replay must succeed before observation. This is best-effort instrumentation, not a
lossless billing ledger: publish observation-error/timeout gaps beside denominators. omi_billing_renewal_observations_total exposes eligible/created/duplicate/projection_error/write_error/timeout deliveries; labels are closed and zero-initialized. These are delivery counts, not distinct invoice/attempt denominators. A timed-out worker may complete later; disclose that uncertainty. Provider livemode is true/false/unknown and production readouts require true.

`expires_at` is 90 days after first observation; readers must exclude expired facts.
No TTL policy or deletion job is installed by this change, so physical cleanup is
not established. Lead2 must settle metadata retention/cleanup before claiming
bounded stored history. For December, read the cohort before the earliest facts
expire; churn-lead reads first coverage within 24 hours of verified serving, then
weekly through December and on 2027-01-08 for December recovery. Lead2/cl2-deploy
own ordinary source delivery; churn-lead never deploys or activates runtime.
No consumer reads or historical backfill are performed; counters describe delivery health only.

Readout: distinct invoice_key and invoice_key/attempt_count among attempted,
positive-due recognized-consumer observations, split month/year/unknown; failed to
paid set transitions, void/uncollectible, raw subscription terminal and scheduled
cancel snapshots. Same-invoice outcomes may span calendar months. A cancellation
scheduled without a renewal invoice is a separate exposure, not a failed attempt.
Unknown coverage, zero-due and unobserved outcomes stay explicit. Export aggregate
cells only; suppress cohorts below ten and complementary small cells.

Focused validation: tests/unit/test_renewal_observations.py plus existing webhook
characterization and delivery tests; no full backend suite.
