# EXP-001 — day-3 re-engagement email

**Status:** pre-registered, not yet started.
**Registered:** 2026-08-30. **Owner:** growth / churn workstream.

This file is the analysis contract. It is pre-registered in the sense that
matters: it is committed **before** the first enrollment, and the job
(`backend/modal/day3_reengagement_email_job.py`) names this path in a constant.
Changing the primary metric or the eligibility predicate after enrollment
begins requires a **new experiment id**, because the assignment salt is the
experiment id and the roster cannot be reconstructed retroactively.

## Hypothesis

A macOS user who signed up, produced something on day 0, then stopped, will
return more often if they receive one email on day 3 showing them what Omi
captured, than if they receive nothing.

## Why this is randomized rather than shipped and measured

The 2026-08-26 cohort study found four behavioral levers with crude retention
risk ratios of 1.9–2.2. Adjusted for week-1 active days by Mantel–Haenszel,
every one collapsed to ~1.05–1.11. Eligibility for any intervention at Omi
correlates with latent engagement, so an unrandomized rollout would produce a
significant and meaningless number. See
`omi-knowledge-base/projects/macos-churn-analysis/`.

## Unit, assignment, split

- **Unit:** authenticated Firebase uid. Assignment unit = analysis unit.
- **Assignment:** `utils/experiments.enroll`, deterministic
  `sha256("EXP-001-day3-reengagement:<uid>")`, persisted to
  `experiments/EXP-001-day3-reengagement/assignments/{uid}`.
- **Split:** 50 / 50, standing. Not a one-shot: the job keeps enrolling
  indefinitely so the underpowered long-horizon metric below accumulates. Drop
  to 90/10 only after a positive primary readout.
- **Enrollment happens before delivery, identically for both arms.** The
  holdout is in PostHog by construction, so it cannot vanish from the
  denominator.

## Eligibility predicate

All of:

1. A macOS signup — `signup_os` in `{macos, mac, mac os x}`. Note this is
   **not** `signup_platform`, which holds only the coarse `desktop` bucket
   shared with Windows; and `signup_os` is the raw client header lowercased
   rather than a canonical value, so it is matched against a set. A bare
   `desktop` is excluded because Windows writes it too.
2. `signup_platform_at` between 72h and 96h before the run (one 24h cohort/day)
3. **Zero conversations created after the day-0 window** (day 0 = 24h from
   `signup_platform_at`)
4. A deliverable email address on the Firebase Auth record
5. Not opted out of lifecycle email, and no prior EXP-001 send

### Why not `last_active_at`, and why not `App Launched`

Both are contaminated by launch-at-login. `record_user_platform` stamps
`last_active_at` on *every authenticated request*, so an auto-launching desktop
app keeps it warm while the user gets nothing; `App Launched` has the same
defect, which is why the churn study reports a strict 14.1% retention next to
its 27.4% headline. Keying "did they come back" on either signal would
systematically exclude the disengaged-but-still-running users this email exists
to reach. Rule 3 uses a **value** signal instead.

This is a coverage choice, not a validity threat — it changes who is eligible,
equally in both arms.

## Treatment

One email, day 3. Content branches on whether the user produced anything on
day 0:

- **Produced output** → personalized: what Omi captured on their first day.
- **No output** → generic first-value tips.

Both branches are the same arm. Randomization balances the mix across arms, so
the pooled estimate is a valid average treatment effect over a heterogeneous
population. The day-0-output stratum is an **exploratory** cut, reported as
exploratory and never promoted to a conclusion — that is the Mantel–Haenszel
lesson applied forward.

Control receives nothing and is never contacted.

## Metrics

**Primary — ≥1 active day in days 3–9 after enrollment.**
Measured baseline for the eligible population: **12.1%** (43/355, PostHog
project 302298, queried 2026-08-30).

**Secondary (monitored, not confirmatory) — day 30–44 retention**, canonical
cohort contract, both definitions (any-explicit-event and strict non-launch).
Measured day-14–23 proxy baseline ~13.2%.

**Guardrails — stop for harm:** lifecycle unsubscribe rate, spam complaint
rate, hard bounce rate.

**Descriptive only:** sent, delivered, bounced, opened. Analysis is
intention-to-treat; the comparison is **never** conditioned on opens. Openers
are the engaged users, so filtering on them reintroduces the confounder the
randomization exists to defeat. Apple Mail Privacy Protection makes opens
largely fiction anyway.

## Power — and the honest limit

Volume: ~160 macOS signups/week (`Onboarding Completed` uniques, last 8 full
weeks: 171, 136, 163, 191, 150, 151, 158, 172). After eligibility, email
availability, and suppression, plan on **~100 enrollments/week**. The
conversation-based rule 3 has not been measured directly, so the job logs the
full eligibility funnel and the first week's real number supersedes this
estimate.

Two-proportion, two-sided α=0.05, power 0.80, 50/50:
`n/arm = 7.85 × [p₀(1−p₀) + p₁(1−p₁)] / Δ²`

| Metric (baseline) | Effect | n/arm | Total | Intake @100/wk | + maturation | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Reactivation (12.1%) | +12pp (2×) | 157 | 314 | ~3 wk | +9d | **~1 month — feasible** |
| Reactivation | +6pp | 554 | 1,108 | ~11 wk | +9d | **~3 months — acceptable ceiling** |
| Reactivation | +4pp | 1,181 | 2,362 | ~24 wk | +9d | not viable |
| D30–44 retention (~13%) | +8pp | 345 | 691 | ~7 wk | +44d | timeline fine, but +8pp from one email is not plausible |
| D30–44 retention | +5pp | 827 | 1,654 | ~17 wk | +44d | ~6 months |
| D30–44 retention | +3pp | 2,183 | 4,366 | ~44 wk | +44d | not viable |

**Stated plainly: this experiment cannot be powered for day-30–44 retention at
any plausible single-email effect size (+1–3pp) in a reasonable timeframe.**
That is why the primary is reactivation — it sits on the causal path to
retention, matures in 9 days, and is genuinely detectable. If the email cannot
move reactivation it certainly does not move retention, and it dies cheaply.
The standing 50/50 split lets the retention question be answered on the
accumulated roster after ~4–6 months without ever having gated shipping on it.

## Readout schedule

- **Interim** at 50% of the 314-enrollment target: report CI only. Stop **only**
  for guardrail harm. Not a success readout.
- **Confirmatory** at 314 enrollments, counting only users whose 9-day window
  has fully elapsed (`assigned_at <= now() - INTERVAL 9 DAY`).
- **Retention readout** no earlier than 6 months, matured
  (`assigned_at <= now() - INTERVAL 44 DAY`).

No dashboard-watching is promoted to a decision. This is cheap to honor: the
primary metric does not exist until day 9 after each send.

## Analysis

Denominator is `Experiment Enrolled` where `experiment_id = 'EXP-001-day3-reengagement'`,
left-joined to subsequent activity. Report the absolute percentage-point
difference with a 95% CI from a two-proportion test. No covariate adjustment —
randomization does that work. No subgroup analysis in the confirmatory readout.

## Kill switch

`DAY3_REENGAGEMENT_EMAIL_ENABLED` must be explicitly true for the job to do any
user work. It fails closed on absent, malformed, or unreadable values: a
deployed job is dark by default.
