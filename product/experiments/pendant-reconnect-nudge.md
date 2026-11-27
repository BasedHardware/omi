# EXP-005 — one reminder after 3 days without a pendant connection

**Status:** pre-registered, not yet started.
**Registered:** 2026-11-27. **Owner:** Goal: Churn.
**Issue:** SCA-4816 (approved by David Zhang, 2026-11-26, anx card:goal-churn).

This file is the analysis contract. It is committed before the first enrollment and
the implementation names this path. Changing the primary metric, the eligibility
predicate, or the split after enrollment begins requires a **new experiment id**,
because the arm is a salted hash of the id and the roster cannot be reconstructed
retroactively.

## Hypothesis

A person with a paired pendant who has not connected it for three days but still
opens the app will reconnect more often if the app shows one reminder on open than
if it shows nothing — and that reconnection reduces subscription cancellation.

## Why randomized

The 2026-11-25 churn-journey read (`omi-workspace data/run-2026-11-25-churn-journeys/README.md`)
found that 78% of paying stoppers still open the app in the week after they stop,
only 9–12% of them visit a device screen, and cancellers cancel a median of 14 days
after they stop. Pendant drop-off is therefore correlated with the same latent
engagement that predicts cancellation, so an unrandomized rollout would produce a
significant and meaningless number. The 50% holdout is what makes the estimate causal.

## Unit, assignment, split

- **Unit:** authenticated Firebase uid. Assignment unit = analysis unit.
- **Assignment:** `sha256('EXP-005-pendant-reconnect-nudge:' + uid)`, first byte
  < 128 → treatment, else holdout. Stable across reinstalls and app versions.
- **Split:** 50/50, standing, not a one-shot; enrollment continues so the
  long-horizon cancel metric accumulates.
- **Enrollment happens before delivery, identically for both arms.** The holdout is
  recorded in PostHog by construction (`Pendant Reconnect Nudge Eligible` with
  `arm=holdout`), so it cannot vanish from the denominator.

**Cap scope (amended 2026-11-27, before enrollment).** The 30-day cap is enforced
per installation, not per account: the timestamp lives in app storage, so a reinstall
or a second phone can receive one more card inside the window. Accepted because the
arm is a uid hash (a reinstall keeps its arm) and an extra card only in treatment
attenuates the measured effect rather than creating it. The readback counts
`Pendant Reconnect Nudge Shown` per uid per 30 days and reports the share of uids
above one; any wider rollout, or graduation after a positive readback, must move the
claim to an authenticated account-level record first.

## Eligibility

All of:

1. A paired pendant (`DeviceType.omi` or `DeviceType.friendPendant`).
2. No successful pendant connection for at least 72 h (`lastPendantConnectedAt`).
3. The app is open — the nudge is evaluated on app open/resume, so eligibility is
   "opens the app while disconnected", not "is disconnected".
4. No reconnect nudge shown in the last 30 days.
5. The other drop-off surface (SCA-4815's one-tap "why did you stop" question) and
   the 24 h sync-stall alert have not fired today. Collision is decided on
   `pendant_dropoff_surface_last_day` (local calendar day), written by both surfaces.

WAL uploads keep sync timestamps fresh while the pendant is disconnected, which is
why eligibility keys on the last *connection*, never `lastSyncTimestamp`.

## Treatment

One dismissible card on Home, shown once per 30 days: reconnect prompt plus an action
that opens the device page. No push (disconnect pushes are ruled out, #3328), no modal,
no second surface. Control receives nothing and is never contacted.

## Metrics

**Primary — pendant reconnection within 7 days of enrollment.** At least one
successful pendant connection (`connected_seconds > 0` for a day, or the device-health
disconnect history showing a live link) in the 7 days after the eligible evaluation.

**Secondary, reported with confidence intervals, not decision-gated — subscription
cancellation within 30 days**, split by tenure band at enrollment (<14 d, 14–59 d,
60 d+) and by paying vs not at enrollment.

Both are reported for treatment vs holdout with a 95% CI from a two-proportion test
(Wilson interval for each arm; difference CI unadjusted, randomization does the work).
Denominator is `Pendant Reconnect Nudge Eligible`, never `Shown` — intention-to-treat.

**Guardrails — stop for harm:** cancellation rate materially worse than holdout at any
interim look, cards dismissed more than 90% of the time with no reconnect lift, and any
rise in notification opt-outs or app uninstalls.

## Power — and what is not knowable yet

The reconnect baseline for the eligible population is **unmeasured**. The eligibility
funnel is logged by the events above; the first week's eligible count and holdout
reconnect rate supersede every estimate below.

Two-proportion, two-sided α=0.05, power 0.80, 50/50:
`n/arm = 7.85 × [p₀(1−p₀) + p₁(1−p₁)] / Δ²`

| Baseline reconnect (7 d) | Effect | n/arm | Total |
| --- | --- | --- | --- |
| 12% | +12 pp (2×) | 157 | 314 |
| 12% | +6 pp | 552 | 1,104 |
| 25% | +10 pp | 326 | 652 |
| 10% | +5 pp | 683 | 1,366 |

At ~100 eligible enrollments per week, the middle rows are 7–11 weeks plus 7 days of
maturation. Stated plainly: a single in-app card cannot plausibly move 30-day
cancellation by a detectable amount. Cancellation is reported because the goal needs
its direction and CI, not because a 30-day readback at this volume can confirm it.

## Readout schedule

- **Interim** at 50% of the primary target: report CI only. Stop **only** for guardrail harm.
- **Confirmatory** at the powered total, counting only enrollments whose 7-day window
  has fully elapsed.
- **Cancellation readout** no earlier than 30 days after each enrollment, matured
  (`enrolled_at <= now() - INTERVAL 30 DAY`); reported as direction plus CI.

No dashboard-watching is promoted to a decision.

## Analysis

Denominator is `Pendant Reconnect Nudge Eligible` by `arm`, left-joined to subsequent
device connection telemetry and to cancellation events. Report absolute
percentage-point differences with 95% CIs. No covariate adjustment. Subgroup cuts
(tenure, paying) are descriptive; the confirmatory readout is the pooled primary only.

## Kill switch

`pendant-reconnect-nudge` (PostHog, read by the app) must be explicitly enabled for
any user work. Absent, inactive, or unreadable reads as off: no evaluation, no event,
no card.
