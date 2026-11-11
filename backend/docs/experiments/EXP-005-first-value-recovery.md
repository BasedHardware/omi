# EXP-005 — first-value recovery for new direct-paid monthly starts

**Status:** pre-registered implementation, dark; no activation, send, merge or rollout is authorized by this file.
**Registered:** 2026-11-11. **Readout:** churn-lead. **Ramp proposals:** goals-coord. **Activation/expansion authority:** David, executed only through lead2/cl2-deploy.

## Bound goal and evidence

Target: monthly paying-subscriber churn of 10%. The supporting proposal's 0.65–1.15 monthly-plan-point scenario is observational, overlapping and non-causal; it is not an expected lift and is not additive with other recovery work. Source evidence: `omi-knowledge-base/projects/omi-100m-plan/evidence/2026-11-11-churn-first-value-recovery-proposal.md` and `2026-11-11-churn-low-engagement.md`.

## Cohort and assignment

- Only newly observed, owner-linked, direct-paid, non-trial monthly Stripe starts with a recognized paid plan enter. Trial, annual, unknown-price, unknown-owner and paid-app starts do not.
- `backend/utils/observability/billing_webhook.py` is already the owner-confirmed post-reconciliation projection. It records `users/{uid}/first_value_starts/{paid_start_hash}` only while both runtime controls are open. No historical scan/backfill exists.
- Assignment is persisted at paid start, before product eligibility or delivery. `sha256("EXP-005-first-value-recovery:<uid>:<subscription_id>:<created>")` selects exactly 50% treatment / 50% control. The experiment id and paid-start key must not change while running. Replayed webhooks cannot redraw or duplicate an enrollment.
- The independent approved-intake draw uses `:approved-intake`. `FIRST_VALUE_RECOVERY_COHORT_PERCENT` changes only intake coverage; it never changes the 50/50 holdout. Analysis is intention-to-treat within each dated intake population.
- The defaults `FIRST_VALUE_RECOVERY_ENABLED=false` and `FIRST_VALUE_RECOVERY_COHORT_PERCENT=0` are both closed. `recovery_enabled()` requires the switch open **and** a positive valid percentage. Off returns before paid-start/user selection, experiment-state writes or dispatch.

## Behavior and clocks

One paid start can receive at most one capture route and one ready-result route across push/in-app surfaces.

1. **Capture recovery:** at `paid_start_at + 72h`, only if no non-discarded/non-deleted/unlocked saved conversation is observed at or after paid start. Next app open claims the in-app prompt. A capture push additionally requires a notification token/timezone, no opt-out, and an actual Omi/Friend Pendant connection observed in the last 24h. It uses the shipped `capture_recovery` / `repair_device` payload and `/settings/device` route.
2. **Ready result:** at `summary_completed_at + 24h`, only when that completed result still exists and has not rendered in Conversation Detail. `summary_completed_at`, not paid start or capture end, is the capture-ready clock. The route uses the shipped `/conversation/{id}` destination. Ready FCM carries no result or user identifier; new clients resolve the exact deep link through authenticated `GET /v1/first-value/recovery/prompt?navigation=true&kind=result`. `/conversations` remains the generic route fallback.
3. A `users/.../first_value_prompts/{kind}` transaction per paid start enforces 30-day dedupe, paid-start expiry, same-subscription/same-price paid coverage, cancellation, paid end, opt-out, local 08:00–22:00 quiet hours, and one first-value prompt per local day. Value/result state is reread in that transaction. Failed/undeliverable attempts do not release the claim into a duplicate send; ordinary product capture/result behavior is unchanged.
4. Background work reads at most 50 due experiment-start rows per existing notifications-job pass, then schedules its next six-hour probe. App open reads at most 12 starts for only that account. Product probes read at most 26 post-paid-start conversations; truncation is unknown coverage and cannot send. Neither path scans the users collection.
5. Re-fetching entitlement/preferences and killing intake cannot make an old assignment eligible. Cancellation/result-open/capture events suppress further prompts. State retention does not create a delivery queue or permit post-30-day sends.

Final copy is provisional and remains an activation gate. Analytics carries only experiment/variant, fixed kind/channel/outcome and timestamps. Push contains fixed routing verbs and generic routes only, never transcript, summary, titles, account identifiers, subscription identifiers or result identifiers.

## Primary and secondary readouts

**Primary at day 7:** among every assigned paid start whose seven-day window has matured, report **both**:
- ≥1 saved capture by `paid_start_at + 7d`;
- ≥1 result opened by `paid_start_at + 7d`, from server-validated rendered Conversation Detail signals.

Report control/treatment numerators, denominators, absolute percentage-point differences and two-proportion 95% CIs separately. Do not collapse them into a composite that can hide a regression. Both assignment arms emit the same fixed-schema value signals; never condition on notification opens.

**Secondary:** time to first saved capture and result open; capture-connected days through day 14. Descriptive delivery eligibility/acceptance by kind/channel. **Day-60 retention:** effective paid end with concurrent control from the churn producer. Day-7 movement never books day-60 churn credit.

**Guardrails:** notification opt-out and quiet-hour/cap suppression; FCM acceptance/errors; cancellation requests and effective paid ends through day 14; capture/upload failures; privacy/content incidents; uninstalls where measurable. Kill new intake and delivery immediately for content/privacy leakage, duplicate prompts or credible cancellation/primary harm. Push acceptance is not proof of device delivery or product value.

## Weekly eligible volume and power — activation blocker

`eligible-volume.md` was absent at implementation time on 2026-11-11. **Weekly eligible volume, baseline day-7 capture/open rates, minimum detectable effect and duration/power are PENDING.** The churn lead must publish these before final PR acceptance/activation; no value is inferred from the selected cancel-flow cohort. If four weeks cannot power a useful primary readout, label this measurement/repair rather than promising a churn answer. Sample-day maturity is added to intake duration; day-60 retention needs another 60 days and is not a ramp gate.

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
3. Backend proves paid-start↔product coverage and index readiness; mobile proves new in-app and ready-push navigation on offline real paths. Existing clients retain ordinary behavior and generic result fallback.
4. Verify false/zero defaults in every environment: no candidate query, experiment write, in-app claim or push. This PR does not add runtime env entries or create production flag-store/PostHog rows.
5. Registry source is `config/feature-flags.yaml` (`FIRST_VALUE_RECOVERY_ENABLED`, `FIRST_VALUE_RECOVERY_COHORT_PERCENT`); rendered reference is `backend/docs/feature-flag-registry.md`. Only lead2/cl2-deploy may set runtime values after David's dated authorization. The enabled switch and positive cohort are checked before query and immediately before FCM.
6. Initial activation is exactly the 2026-11-18 10% cohort. Confirm counts remain aggregate (cells below 10 reported as `<10`) and logs contain no user/conversation/subscription identifiers.
7. Read back assignment parity, duplicate suppression, opt-out/cancellation suppression, quiet-hour/cap behavior, day-7 outcomes and guardrails before every expansion.

## Rollback

Set `FIRST_VALUE_RECOVERY_ENABLED=false` or `FIRST_VALUE_RECOVERY_COHORT_PERCENT=0` through the authorized operator path. Do not delete historical assignments/claims or change capture/result entitlements. This stops selection, in-app claims and immediate dispatch; an already accepted FCM cannot be recalled. Ship/revert the mobile artifact only if client behavior itself is implicated. Resume requires a new dated authorization and never re-randomizes a paid start.
