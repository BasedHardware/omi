# Ladder v1 cutover

This PR is draft. Every switch below is unset/OFF by default. It makes no Stripe,
deployment, GCP, or customer-data change. Retained legacy prices and their catalog
allocations remain unchanged. Free has ladder policy when the relevant admission
switch is enabled. Annual budgets reset monthly at midnight UTC on the first.

## Price binding

The catalog declares six lookup keys: `ladder_v1_{plus,pro,architect}_{month,year}`.
Each maps to a separate runtime env binding:
`LADDER_V1_{PLUS,PRO,ARCHITECT}_{MONTH,YEAR}_PRICE_ID`.
No placeholder price is sold. Missing bindings hide paid offers under the existing
v2 contract. Binding a real ID is a configuration change; no code release is needed.
Binding to a retained legacy price, duplicating IDs, conflicting product ownership,
or replacing a legacy billing env ID is rejected. Recognition of a bound ladder
price does not depend on the storefront switch, so renewals retain their identity
on rollback. Binding env vars must remain present while subscribers use those IDs.

Only `STOREFRONT_LADDER_V1_ENABLED=true` admits purchases of those IDs. The existing
v1 purchase catalog and its platform partition stay compatible with installed
clients. The v2 sheet offers the unified ladder on all platforms. Checkout and
storefront reads attest active USD recurring prices, the declared lookup key,
product ownership, month/year interval and interval count 1. Stripe is the amount
authority. Legacy subscribers cannot directly post a ladder price to migrate.

David must approve and create all six prices on the existing Plus, Operator and
Architect products before binding them. Proposed amounts and 10× yearly prices
are in the approved program Stripe plan; this code does not write those objects.
Validate those amounts and lookup keys using an approved read-only receipt before
ramping. Keep every existing price and legacy env binding intact.

## Switches and admission

| Switch | Effect |
| --- | --- |
| `STOREFRONT_LADDER_V1_ENABLED` | Existing v2 presentation endpoint; admits bound ladder checkout IDs |
| `LADDER_V1_LANE_METERING_ENABLED` | Adds live/batch/on-device/unknown shadow attribution to existing hourly writes |
| `LADDER_V1_BUDGET_ENFORCEMENT_ENABLED` | Shared monthly ledger admission for Free and ladder-price accounts; legacy bypass |
| `LADDER_V1_PRO_GATES_ENABLED` | Pro/Architect proactive producers, managed screen context and cloud screen vectors; Plus core desktop |
| `LADDER_V1_MCP_DAILY_CAPS_ENABLED` | Atomic shared daily request cap across MCP and developer keys: 100/500/5,000/5,000 |
| `LADDER_V1_WIRE_IDENTITY_ENABLED` | Uses approved `LADDER_V1_MIN_MOBILE_VERSION` and `LADDER_V1_MIN_WINDOWS_VERSION` floors |
| `LADDER_V1_RETIRE_PRO_ALIAS_ENABLED` | Rejects retired `pro` alias; enable only after old-client retirement and stored-row audit |
| `HELD_CONTENT_ENABLED` | Existing choice API, additionally requires `X-Omi-Held-Content: 1` |

Exact `true` enables new switches. Identity floors remain conservative when no
approved version is configured. Existing `X-Omi-Plan-Identity: 1` capability and
macOS floor are retained. Alias retirement is a separate last step: leave it OFF
while any installed caller or stored subscription requires `pro` as Architect.
It never turns `pro` into the new Pro ID; new Pro is always `operator`.

Below 100% managed work is admitted; 80% remains a nudge in the existing usage
payload. At 100% managed work pauses. Chat admission returns structured 402
`usage_budget_exhausted`, `trigger=usage_budget`, reset/period and choices
`on_device`/`upgrade`. Sync v1/v2 accept exhausted uploads only after durable
server custody, then recover only after explicit backlog choice (or a fitting
upgrade intent) through the fenced held-audio state machine. Suppressed live PCM uses that same encrypted store; the client
WAL is unchanged. See [dispatch custody](stt-cap-dispatch.md) for storage bounds,
recovery and crash limitations. No new transcript lock is created by ladder
exhaustion. In-flight work can finish; projection admission is not a prepaid
reservation.

`/v1/users/budget-choice` recognizes ladder exhaustion and persists the existing
monthly choice record. Upgrade intent grants no entitlement. Ask-once semantics
and choice reset are unchanged. Capture, held content, on-device transcription and
on-device summaries continue. Every source defers Omi-paid structuring, memories,
action items, embeddings, apps and titles at cap; generated/background producers
skip via the shared funded gate. The stored transcript stays visible. Chat pauses at 100% until the monthly reset or an
upgrade on every ladder tier, including Free (David ruling October 14 evening).
The existing budget-enforcement flag gates this policy; legacy prices retain their
existing behavior. There is no fallback chat model or fallback chat allowance.
The additive `chat_at_cap` payload owns the pause, reset-date and upgrade copy;
clients display it at the composer and open plans with `trigger=usage_budget`.

The additive v2 `at_cap` payload is emitted only when enforcement is on and a
non-legacy account is exhausted. It owns title/body/buttons/checkbox and
`Upgrade to Pro for speaker separation and higher accuracy`. The backend golden
is `backend/tests/fixtures/ladder_v1_at_cap.json`. Existing goldens are unchanged
when the field is absent. Pro receives Architect checkout only on the exhausted
`usage_budget` surface, per the existing presentation contract.

Daily API reservations are transactional per UID, not per key. The final allowed
request reaches the cap; the next request receives structured 429 reset/upgrade
metadata. At 80%, successful REST responses carry `X-Omi-Usage-State: nudge`,
`X-Omi-Usage-Reset-At` and `X-Omi-Storefront-Trigger: mcp_daily_cap`; hosted tool
results carry `_meta.omi_usage`. At 100%, hosted MCP preserves the structured error
there too. The existing hourly abuse limits and scope checks remain in place.
Daily store errors return retryable 503; no free capacity is granted on outage.

## Lane-aware shadow accounting

One blended budget remains authoritative, rather than independent transcription
and chat caps. `shadow_v1.lanes.live` measures managed streaming speech reaching
the provider (`source=listen`); its accepted speech seconds divided by 3,600 are
live hours. Sync v1/v2 and the prerecorded proxy draw batch transcription units.
On-device funding draws zero transcription units. Cloud extraction from an
on-device transcript draws only its normal LLM attempt units, never another STT
charge. Unknown sources remain unknown rather than being mislabeled live.
Lane totals are diagnostic subdivisions, never additional charges; the existing
feature/funding projection is summed once. Metered API infra lives in
`users/{uid}/ladder_v1_api_days/{UTC-date}` and joins the monthly projection only
for ladder entitlements. Model work from API tools remains separately metered.

The shadow projection is still a **partial lower bound**. Direct LLM paths,
best-effort gateway delivery, STT paths without hourly writers, vendor request
fees and older unprojected events remain visible completeness gaps. The managed streaming session now forwards its accepted-send VAD speech delta
(including fractions of seconds, excluding replay) to hourly pricing. Older live
paths remain elapsed-time/ratio estimates and have no claimed accepted live hours.
Lane labels are not retroactively inferred. Do not flip enforcement until coverage and
observed ledger cost are accepted; this draft does not assert complete billing
or strict concurrent-spend prevention. Architect's 189,463 units continue to use
the existing break-even derivation; no budget was changed in this PR.

## Ramp and rollback checklist

1. Merge/integrate the client storefront and #21466 lanes into this draft; validate
   mobile and desktop on-device holding, retry, choice persistence and recovery.
2. Establish the two-week measurement baseline; verify producer coverage, fixed
   rate-card economics and monthly reset behavior in a test environment.
3. David approves Stripe writes; create six prices, approve read-only identity/
   amount receipts, bind IDs without editing any legacy env var.
4. Turn on lane shadow metering first; review live/batch funding and extraction
   accounting before enabling budget enforcement.
5. Confirm shipped unknown-plan decoders; configure real mobile/Windows floors;
   enable wire identity. Keep alias retirement off until the long tail is retired.
6. Ramp v2 storefront **web → mobile → desktop**, using each client's default-off
   storefront/upsell flags. Server flags are global: platform ramp belongs to
   client delivery/flags, not a client-supplied entitlement header.
7. Enable held-content and then budget/Pro/MCP mechanics only after integrated
   client acceptance; review ARPMAU, conversion, payer retention, cap/held/reset
   outcomes and ledger completeness at each step. No agent flips these flags.
8. Retire the `pro` alias last, after stored records and old callers are safe.

Rollback: turn off storefront/client upsell flags to stop new sales; retain price
bindings and all retained prices for webhook recognition and renewal. Turn off
budget, Pro, daily-cap and identity switches independently to restore the legacy
admission paths. Restore alias acceptance immediately if a decoder/stored-row
regression appears. Never rewrite legacy subscription prices, usage history or
captured content. The existing default-off reset-recovery switch can unlock
already-processed locked content under its runbook. It never grants consent to
process held audio or deferred transcripts; this PR does not enable it.


## Efficiency admission gate (David, 2026-10-14 later ruling)

Do not flip `STOREFRONT_LADDER_V1_ENABLED` until the batch/background lane is live,
its fully loaded worn-hour cost has been measured, and the versioned 98% background /
2% live blend supports the copy bands. Pro 720 hours on one device needs at most
about $0.052/worn hour; Plus 240 hours needs at most about $0.058/worn hour.
Use the actual configured budget and 0.85 recording share to validate both thresholds.
A vendor-only batch STT estimate is insufficient: include summaries, memories, apps and infra.

`rate_card_v2.json` owns the lane-specific advertised rates. Both cloud lanes remain
130 units/hour provisionally, preserving 100 / 280 / 1,200 hours today. On-device
transcription is zero units; cloud processing of its text still consumes LLM units.
V1 event pricing and its digest remain unchanged. Replace the measured batch value in
an approved new versioned card (and pin its digest); live capacity stays separate.
Plus switches bands at 240 hours, Pro at 720, Architect at 1,440 (two full devices).
Below these thresholds, the existing per-day copy remains. This is presentation capacity,
not a new independent live budget or a completeness claim about the usage ledger.

Supported capacity thresholds survive nice rounding: if actual capacity supports
720 hours, the headline and remaining-hours meter both show 720 rather than rounding
the meter down to 700. Display-percent rounding never promotes a sub-100% budget
into the exhausted/Architect surface.


## Funded halt and user-chosen backlog (David, 2026-10-18)

Both existing admission flags also gate funded conversation and generated work:
`STT_CAP_DISPATCH_ENFORCEMENT` applies the finite legacy plan allowance (using
both speech and transcription usage); `LADDER_V1_BUDGET_ENFORCEMENT_ENABLED`
applies blended units to Free/ladder entitlements. No tier bypasses its funded
limit. Legacy prices retain their catalog identity; ladder-only activation retains
its existing legacy-dispatch bypass. Both off invokes the original paths and
omits `processing_backlog` and new false conversation markers in actual FastAPI JSON.

On-device and custom-STT transcripts are stored with `processing_deferred=true`,
completed capture status and no generated side effects. First-open, reset, generic
reprocess and background retries do not consume that backlog. New recordings
process normally after reset. The additive subscription `processing_backlog`
combines exact held totals with one transactionally maintained deferred-text total.
It owns counts, seconds, estimated units, allowance-equivalent hours, percent,
remaining units, exceeds_remaining and capped/waiting_choice/processing/none state.
`budget_exhausted` distinguishes a confirmed limit from an unavailable allowance;
unknown allowance pauses funded work without claiming the user spent the limit.
Held audio uses the provisional fully loaded batch rate; text uses eight standard
model-work bundles per 12,000 transcript characters (minimum one bundle). Estimates
are planning estimates, not reserved credits or vendor invoices.

`POST /v1/users/processing-backlog/process` requires authentication and a stable
`Idempotency-Key` per confirmed choice. Month, cutoff, cursors, estimate balance,
reserved attempt and renewable token-fenced lease persist on the job. Two bounded
newest-first pages merge audio and text by capture time. Items that do not fit stay
waiting; smaller older items may fit. Existing audio reconciliation receipts and
claims remain authoritative. A previous month's choice never funds a new month.
Checkout and immediate plan changes start a run only when its whole estimate fits;
monthly renewal does not mint backlog intent. Declined/empty upgrade estimates
also get an idempotency receipt, so a later retry cannot auto-spend after reset. No retention/deletion policy changes.

Subscription adds one deferred-summary document read to the existing one held
summary plus <=20 held-row reads; enabled monthly counter reporting now shares a
closed-hour cache (one open-hour read on warm requests), so processing-status polls
do not rescan every hourly document; there is no deferred-conversation list query on
that route. Capped conversation admission reads one current legacy usage hour, or
three current ladder hour/day documents, plus subscription/cache-dependent reads;
its atomic backlog transition adds one item read and two writes to the existing
conversation transaction. Cold/evicted sessions and 900-second reconciliation read
H monthly hourly documents (+2D elapsed-day documents for ladder); they retain only
closed-bucket sums. Hour/day rollover closes old buckets once. A bounded 1,024-user
process cache and per-operation scope share these snapshots across fanout. These
are admission snapshots, not distributed spend reservations; admitted work can drain.
