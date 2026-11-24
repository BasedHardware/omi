# SCA-2190 guarded re-land and comparison packet

Source preparation authorized by cost lead 2026-11-15 04:24Z, through 10:18:30Z.
This is one source candidate: restore the previously reviewed #25285 change plus
an admission fence and its prerequisite comparison configuration. Release owns
canonical admission and production. No worker image roll, live mutation, migration
or owner-memo enforcement is authorized here. Shadow-only work books $0 saving.

## Contract and source admission fence

Every owner memo use still reads the durable token inside the authorizing
transaction and matches token, server revision and generation. Never cache BLOCK;
unreadable authority falls through to live. Keep the prepare-wide 256-document
budget, including successful and refused redirects, and the fail-closed kill
switch `ops_kill_switches/privacy_decision_cache.disabled` (30-second polling).

New `bpp_owner_memo_enforce` is a key in the existing FIRESTORE_READ_LEVERS map,
not a new environment variable or budget slot. It defaults to 0. Both the outer
selection and the inner owner path require this explicit admission for serving;
shadow candidates bypass only this admission, never token certification or the
kill switch. Nonzero fleet shadow still suppresses all owner enforcement even
if a future configuration mistakenly enables admission. A changed image with
old, missing, invalid or empty configuration cannot serve an owner-memo decision.
The previously shipped id-set memo retains its existing levers and semantics.
A later reviewed admission config requires cost-lead GO; this PR supplies none.

## Later API admission supersedes this historical packet

The 2026-11-17 O2b stage-2 order separately admitted prod backend, backend-sync
and backend-integration to owner enforcement 100/shadow 0/decision cache 0.
The source-only re-land below did not grant that admission. Its default-off code
fence and other consumer exclusions remain intact; the original per-surface
snapshot below is historical. See the [current API admission and inverse](runbooks/privacy-check-shadow.md#current-api-owner-memo-admission-2026-11-17)
and [current source role split](../deploy/runtime_env/README.md#api-owner-memo-source-carry-o2b-2026-11-17).

## Per-surface packet

| Consumer | Source disposition | Admission/readback owner |
| --- | --- | --- |
| backend, backend-sync, backend-integration, backend-sync-backfill | shadow 10, negative-cache 0, ttl60 0, owner-enforce 0; every other lever unchanged | Release reads actual traffic-receiving revisions, not templates |
| batch-pipeline worker | same privacy comparison map; preserve monthly-reader 0/0 and every other lever | Existing next-worker-train owner via SCA-2176 / SCA-2173; no roll requested |
| listen / pusher | no source lever changes; owner-enforce defaults 0 even where shadow is 0 | Remain excluded from owner enforcement; qualify transactional paths before any later admission |
| desktop backend / Cloud Run jobs / operator producers / other image consumers | same default-off code admission; no source lever changes | Remain excluded; no inference that they lack transactions or never call batch authority |

The generated read-lever manifest enumerates every configured surface with
owner-enforce 0. This source inventory is not an effective production receipt.
Release must prove shadow >0 on all four batch callers before admitting the
re-land, despite the defense-in-depth code fence. SCA-2225's parser correction,
protected-environment disposition and installed executor/source binding remain
production prerequisites, independently of controller CI. Worker comparison
coverage starts only on its existing train; do not claim all-plane qualification
before it and all other admitted writer planes have receipts.

## Qualification window and positive evidence

Do not substitute the six-hour push or a clean hour for qualification. Preserve
the checked-in privacy-check-shadow runbook's **at least 14 days of all-plane
shadow with zero unexplained mismatches**, plus its emulator writer matrix and
privacy contracts. This also exceeds the historical SCA-2190 one-day staging
proposal; without an explicit newer window ruling, the longer requirement wins.
A clean first hour is a readiness observation only. Cost lead owns acceptance
and any authoritative window amendment; no shortening is inferred here.

Observe positive `privacy_owner_comparison_total{shape,candidate_source="owner_hit",result="match"}`
for attempt, no_attempt and snapshots on each relevant surface, corroborated by
`privacy_decision_comparison_total`. Both counters are retained by the Cloud Run
scrape keep-lists, isolated sync-worker fold and batch-worker registry. Require
`privacy_decision_mismatch_total{family="batch",reason="stale_allow"}` and
`privacy_shadow_checks_total{family="batch",result="mismatch"}` zero. Also require
`privacy_negative_lookup_total{result="mismatch"}` zero, no unresolved shadow
errors, and no scrape gaps. A zero denominator is NOT evidence. Existing metrics
have counts-only bounded labels; do not add identifiers. Candidate snapshots are
throwaway exports; actual callers retain live rows. The unit regression warms
real owner candidates on all three shapes while admission stays off.

Verify invalidation through token rotation on privacy/account-deletion/authority
changes, token/schema/server-revision failures, BLOCK and redirect bounds. Check
the kill switch on and unreadable: neither may serve an owner candidate or allow.
Existing privacy suites cover those contracts; new regressions cover image-before-
config and warmed-cache admission failures. Production/emulator receipts remain
release/verification work; synthetic unit tests do not substitute for them.

## Expiry, rollback and economics

Partial-value source expiry is 2026-11-17 (UTC), two days after preparation.
This is a validator deadline, not an automatic live lever reset. Cost lead must
renew the dated records through review before that date to complete a 14-day
window; expiry must never clear shadow or enable admission automatically.

Rollback: keep owner-enforce=0; Release may set the existing kill document's
`disabled` to true (or restore the previous source image) through its existing
controlled authority. To stop comparison overhead, restore the recorded baseline
per-surface shadow/negative-cache settings from the pre-change source and actual
revision receipt, keeping owner-enforce=0 and ttl60=0. A source rollback reverts
this combined candidate; no data migration or deletion is needed.

Expected owner-memo saving remains an estimate (~$60/day at the historical 44%
hit rate, up to ~$105/day at 80% repeat-owner reuse), contingent on qualification
and enforcement GO. The comparison window instead adds reads: sampled calls
pay the live walk plus observation token and candidate walk/token; unsampled
calls have no owner-memo saving. Capture before/after reads by caller and completed
audio-hour separately from shadow mode, plus hit rates and mismatch denominators.
No full-day or post-enforcement production number has been measured here.

Within the six-hour window: source/config packet, focused safety regressions,
independent exact-head delta privacy review and CI can be delivered. Canonical
admission waits on SCA-2225 and effective configuration proof. Full qualification,
enforcement and booked savings cannot complete in six hours under this window.
