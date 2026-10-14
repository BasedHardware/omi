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
payload. At 100% managed work pauses. Chat and raw sync admission return structured
402 `usage_budget_exhausted`, `trigger=usage_budget`, reset/period and choices
`on_device`/`upgrade`. Raw sync refuses before consuming the upload: the device WAL
remains the recording authority, waiting for the choice/reset/upgrade. No new lock
is created by a ladder budget exhaustion. This is not a server-accepted audio job.
In-flight work can finish; projection admission is not a prepaid reservation.

`/v1/users/budget-choice` recognizes ladder exhaustion and persists the existing
monthly choice record. Upgrade intent grants no entitlement. Ask-once semantics
and choice reset are unchanged. On-device processing and summary/chat fallback
remain owned by the on-device lane (#21466); integrate that lane before enabling
budget enforcement. Its cheap-chat model/cap still requires David's ruling.

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
captured content. Existing reset recovery has its own default-off switch and
requires its documented runbook; this PR does not enable it.


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

Cheap fallback chat model/cap at the shared budget remains OPEN for David's ruling.

Supported capacity thresholds survive nice rounding: if actual capacity supports
720 hours, the headline and remaining-hours meter both show 720 rather than rounding
the meter down to 700. Display-percent rounding never promotes a sub-100% budget
into the exhausted/Architect surface.
