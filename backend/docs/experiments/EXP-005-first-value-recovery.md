# EXP-005 — first-value recovery for new direct-paid monthly starts

**Status:** pre-registered implementation, dark; no activation, send, merge or rollout is authorized by this file.
**Registered:** 2026-11-11. **Readout:** churn-lead. **Ramp proposals:** goals-coord. **Activation/expansion authority:** David, executed only through lead2/cl2-deploy.

## Bound goal and evidence

Target: monthly paying-subscriber churn of 10%. The supporting proposal's 0.65–1.15 monthly-plan-point scenario is observational, overlapping and non-causal; it is not an expected lift and is not additive with other recovery work. Source evidence: `omi-knowledge-base/projects/omi-100m-plan/evidence/2026-11-11-churn-first-value-recovery-proposal.md` and `2026-11-11-churn-low-engagement.md`.

## Cohort and assignment

- Only newly observed, owner-linked, direct-paid, non-trial monthly Stripe starts with a recognized paid plan enter. The subscription must contain exactly one item. Its single latest invoice must be owner/subscription-matched, `billing_reason=subscription_create`, `status=paid` and have `amount_paid > 0`; exactly one positive subscription invoice line must match that subscription item and recognized monthly price, so another item cannot fund a free recurring line. The experiment clock is its `status_transitions.paid_at`, never subscription creation or entitlement activation. Creator-app metadata, trial/trial conversion, renewal, same-subscription reactivation, replacement with an existing paid subscription, annual/multi-month, unknown-price, unknown-owner and $0/bundle-funded starts do not qualify. This is paid-invoice evidence only, not proof of cash/bank settlement.
- `backend/utils/observability/billing_webhook.py` is already the owner-confirmed post-reconciliation projection. While the runtime controls are open, a structurally new candidate gets at most one `latest_invoice` retrieve with an explicit five-second SDK timeout and zero retries. FastAPI schedules the sync post-response callback before any provider retrieval, so invoice proof never delays webhook acknowledgement; direct Python callers use `stripe_executor`. Failure or missing proof excludes the start without affecting ordinary billing telemetry. Expanded invoice evidence avoids a provider read. OFF performs no proof retrieval, Firestore selection or experiment write. No historical scan/backfill exists.
- Assignment is persisted at paid start, before product eligibility or delivery. `sha256("EXP-005-first-value-recovery:<uid>:<subscription_id>:<invoice_paid_at>")` selects exactly 50% treatment / 50% control. The experiment id and paid-start key must not change while running. Replayed webhooks cannot redraw or duplicate an enrollment.
- The independent approved-intake draw uses `:approved-intake`. `FIRST_VALUE_RECOVERY_COHORT_PERCENT` changes only intake coverage; it never changes the 50/50 holdout. Analysis is intention-to-treat within each dated intake population.
- The defaults `FIRST_VALUE_RECOVERY_ENABLED=false` and `FIRST_VALUE_RECOVERY_COHORT_PERCENT=0` are both closed. `recovery_enabled()` requires the switch open **and** a positive valid percentage. Off returns before paid-start/user selection, experiment-state writes or dispatch.

## Behavior and clocks

One paid start can receive at most one capture route and one ready-result route across push/in-app surfaces.

1. **Capture recovery:** at `paid_start_at + 72h`, only if no non-failed/non-hidden/non-discarded/non-deleted/unlocked saved conversation is observed at or after paid start. Next app open claims the in-app prompt. A capture push additionally requires a notification token/timezone, no opt-out, and an actual Omi/Friend Pendant connection observed in the last 24h. It uses the shipped `capture_recovery` / `repair_device` payload and `/settings/device` route.
2. **Ready result:** at `summary_completed_at + 24h`, only when that completed result still exists and has not rendered in Conversation Detail. `summary_completed_at`, not paid start or capture end, is the capture-ready clock. The route uses the shipped `/conversation/{id}` destination. Ready FCM carries no result or user identifier; protocol-1 mobile clients resolve the exact deep link through authenticated `GET /v1/first-value/recovery/prompt?navigation=true&kind=result`. `/conversations` remains a generic safe-route fallback, not proof of exact-result support.
3. **Supported-client fence:** only the new Flutter checkout claims with `X-Omi-First-Value-Protocol: 1`. A normal app open or resumed Home checks the prompt; it also reports the actual notification permission and IANA timezone through the existing notification service. The per-start capability and granted-permission timestamps must be at most 24h old for push, and the claim transaction rechecks them. Missing/denied permission, missing/invalid timezone, old clients, desktop and unknown capability receive no in-app claim or push. Pendant reports refresh the same fence. The protocol header alone does not grant entitlement or fabricate a result: server billing, ownership, value and result probes remain authoritative.
4. A `users/.../first_value_prompts/{kind}` transaction per paid start enforces 30-day dedupe, paid-start expiry, same-subscription/same-price paid coverage, cancellation, paid end, opt-out, local 08:00–22:00 quiet hours, and one first-value prompt per local day. Value/result state is reread in that transaction. Failed/undeliverable attempts do not release the claim into a duplicate send; ordinary product capture/result behavior is unchanged.
5. Background work reads at most 50 due experiment-start rows per existing notifications-job pass, then schedules its next six-hour probe. App open reads at most 12 starts for only that account. Product probes read at most 26 post-paid-start conversations; truncation is unknown coverage and cannot send. Neither path scans the users collection. Controls use identical value probes and can never claim a prompt.
6. Entitlement/preference changes and killing intake cannot make an old assignment eligible. Authoritative saved-conversation state and the actual rendered Conversation Detail callback—not prompt CTA clicks—suppress further prompts in both arms. Result-open signals for existing assignments remain recordable after a kill/rollback; cohort queries and new delivery stop, so capture readout after rollback requires an independent readout probe. State retention does not create a delivery queue or permit post-30-day sends.

Final copy is provisional and remains an activation gate. Analytics carries only experiment/variant, fixed kind/channel/outcome and timestamps. Push contains fixed routing verbs and generic routes only, never transcript, summary, titles, account identifiers, subscription identifiers or result identifiers.

## Primary and secondary readouts

**Primary at day 7:** among every assigned paid start whose seven-day window has matured, report **both**:
- ≥1 saved capture by `paid_start_at + 7d`;
- ≥1 result opened by `paid_start_at + 7d`, from server-validated rendered Conversation Detail signals.

Report control/treatment numerators, denominators, absolute percentage-point differences and two-proportion 95% CIs separately. Do not collapse them into a composite that can hide a regression. Both assignment arms emit the same fixed-schema value signals; never condition on notification opens.

**Secondary:** time to first saved capture and result open; capture-connected days through day 14. Descriptive delivery eligibility/acceptance by kind/channel. **Day-60 retention:** effective paid end with concurrent control from the churn producer. Day-7 movement never books day-60 churn credit.

**Guardrails:** notification opt-out and quiet-hour/cap suppression; FCM acceptance/errors; cancellation requests and effective paid ends through day 14; capture/upload failures; privacy/content incidents; uninstalls where measurable. Kill new intake and delivery immediately for content/privacy leakage, duplicate prompts or credible cancellation/primary harm. Push acceptance is not proof of device delivery or product value.

## Weekly eligible volume and power — activation blocker

Measured screening record: `omi-workspace:data/run-2026-11-11-goals/churn-round5/eligible-volume.md`, generated 2026-11-11T01:47:21Z from three read-only aggregate HogQL queries. Fully mature UTC starts from 2026-10-14 through 2026-11-04 yielded 71 either-route screening candidates over three weeks (**23.7/week**), or **18.5/week** over the latest two windows. These are behavioral proxies, **not exact runtime-eligible or send volume**, and can err in either direction. Positive paid-invoice proof, supported protocol-1 client, consent/timezone, actual ready/open linkage, recent pendant and caps are not jointly represented. Exact predicate volume and paid-start↔product/protocol coverage remain activation blockers, not zero and not this proxy.

At the proxy candidate rate and equal 50/50 assignment, a four-week all-cohort exposure gives about 95 candidates (47/arm) and only about a **29-percentage-point** worst-case-normal-approximation MDE at two-sided alpha .05/80% power; the latest-two-week rate gives about 74 candidates and **33 points**. A 10-point difference needs approximately 392/arm (784 total), roughly **33–42 weeks even at full proxy-candidate exposure** before maturity/exclusions. ITT-over-all-observed-start scenarios have about 14–18-point MDEs over four weeks, but those are not eligible-send estimates. Baseline day-7 rates from the implemented runtime measurement are still **PENDING**. Early ramp is measurement/repair, not a churn decision or promised lift. Sample-day maturity is added to intake duration; day-60 effective-end retention needs its own baseline and longer observation and is not a ramp shortcut.

## Dated ramp and stop gates

| Date | Gate / allowed action |
| --- | --- |
| 2026-11-16 | David decides activation, product/legal classification, readout ownership, final copy, coverage and power. Every flag stays unset/default if any item is missing. |
| 2026-11-17 | If approval is absent or incomplete, remain dark and churn-lead records the blocker. |
| 2026-11-18 | Conditional first eligible cohort only after David's approval: enable backend/mobile artifacts and set intake to **10%**. Permanent 50/50 control. No other percentage is authorized. |
| 2026-11-25 | Churn-lead reads delivery/privacy/opt-out/cancellation guardrails and matured day-7 capture **and** result-open outcomes. goals-coord may propose **50%** only after a clean readout and power re-check; David authorizes through lead2/cl2-deploy or it stays at 10%. |
| 2026-12-02 | Re-read matured outcomes and powered measurement. goals-coord may propose **100%** only after David's authorization through lead2/cl2-deploy. Keep the 50/50 holdout throughout; no day-7-to-churn credit. |
| Day 60 after each intake | Measure effective-end retention against concurrent control. No automatic expansion or success declaration. |

## Explicit activation checklist

1. churn-lead supplies eligible weekly volume, baselines, powered sample/readout dates and the day-60 producer join.
2. goals-coord records product/legal admission, named readout owner and final copy approval.
3. Backend proves positive-invoice paid-start↔product coverage, supported protocol/permission coverage and index readiness; mobile proves new in-app and exact ready-push navigation on offline real paths. Desktop, old clients and unknown measurement coverage stay unserved and must be reported separately, not relabeled eligible.
4. Verify false/zero defaults in every environment: no candidate query, experiment write, in-app claim or push. This PR does not add runtime env entries or create production flag-store/PostHog rows.
5. Registry source is `config/feature-flags.yaml` (`FIRST_VALUE_RECOVERY_ENABLED`, `FIRST_VALUE_RECOVERY_COHORT_PERCENT`); rendered reference is `backend/docs/feature-flag-registry.md`. Only lead2/cl2-deploy may set runtime values after David's dated authorization. The enabled switch and positive cohort are checked before query and immediately before FCM.
6. Initial activation is exactly the 2026-11-18 10% cohort. Confirm counts remain aggregate (cells below 10 reported as `<10`) and logs contain no user/conversation/subscription identifiers.
7. Read back assignment parity, duplicate suppression, opt-out/cancellation suppression, quiet-hour/cap behavior, day-7 outcomes and guardrails before every expansion.

## Rollback

Set `FIRST_VALUE_RECOVERY_ENABLED=false` or `FIRST_VALUE_RECOVERY_COHORT_PERCENT=0` through the authorized operator path. Do not delete historical assignments/claims or change capture/result entitlements. This stops selection, in-app claims and immediate dispatch; authenticated result-open outcomes already emitted by the client remain recordable, while an already accepted FCM cannot be recalled. Ship/revert the mobile artifact only if client behavior itself is implicated. Resume requires a new dated authorization and never re-randomizes a paid start.
