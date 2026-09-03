# EXP-002 — desktop identity: memory, not assistant (`control` vs `memory_v1`)

**Status:** pre-registered, not started. First enrollment happens only after
this merges, the Beta build containing it ships, and
`exp-002-desktop-identity-v1` is set true in PostHog.
**Registered:** 2026-09-03. **Owner:** desktop identity workstream.
**Registry:** `backend/config/desktop_experiments.py` names this file's
experiment id, arms, flag keys, channel, and version floor.

This is the analysis contract. It is committed **before** the first
enrollment, on the substrate of [`utils/experiments.py`](../../utils/experiments.py)
and the
[experimentation-substrate decision](../../../omi-knowledge/projects/macos-churn-analysis/decisions/2026-08-30-experimentation-substrate.md)
(uid unit, deterministic draw, persisted assignment, both arms enrolled in
one code path before treatment, intention-to-treat). Changing the primary
metric, arm set, or eligibility after enrollment begins requires a **new
experiment id**, because the assignment salt is the experiment id and the
roster cannot be reconstructed retroactively. **Never rename this id.**

## Hypothesis

A macOS user for whom Omi behaves as *memory, not assistant* — the daily
postcard is the home object, Interject is on, the proactive director is
quiet, and generic web Q&A is starved — gets more value out of their own
captured day than a user of today's assistant-chrome, measured on the causal
path to retention rather than retention itself.

## Arms and assignment

- **Unit:** authenticated Firebase uid. Assignment unit = analysis unit.
- **Arms (v1):** `control` weight 1.0, `memory_v1` weight 1.0 — equal split.
  Adding a third arm later is a registry change in
  `config/desktop_experiments.py` (name + weight), not a new enroll path;
  the draw partitions buckets in list order.
- **Assignment:** `POST /v1/desktop/experiments/enroll`
  (`routers/desktop_experiments.py`), deterministic
  `sha256("EXP-002-desktop-identity-memory-v1:<uid>")`, persisted to
  `experiments/EXP-002-desktop-identity-memory-v1/assignments/{uid}` on the
  customer data plane.
- **Enrollment before paint:** the desktop app holds its shell on the
  launch splash until the enroll call settles, signed-in, both arms, one
  code path. The server emits `Experiment Enrolled` before responding, so
  the event lands before any treatment UI. Fail-closed everywhere: a gate
  refusal, persist failure, plane failure, or timeout paints `control` and
  delivers no arm.
- **Exposure (v1):** Beta bundle only (`com.omi.computer-macos.beta`),
  app version ≥ the floor in the registry. Stable, dev, and named bundles
  do not enroll. Named bundles dogfood arms through
  `OMI_FORCE_EXPERIMENT_VARIANT` locally — that override applies chrome,
  never writes assignments, and tags events with `experiment_forced: true`.

### Treatment definition (`memory_v1`)

Wiring and defaults only — no new product surface:

1. **Postcard-first.** The daily summary / `memories_learned` review card is
   the landing object: the chat surface opens on the postcard when a new
   summary exists (arm-gated INV-CHAT-2 admission seed), and the hub stage
   leads with the postcard section. Chat remains fully available.
2. **Interject on**, through the existing merged flag path
   (`desktop_interject` / `desktop_interject_kill`): armed users get
   Interject == (arm == memory_v1); the fleet kill switch still disarms
   every arm.
3. **Director starved.** The context-director pipeline
   (`ContextBucketsFeature.isEnabled`) returns false for this arm — the
   existing gate, not a new director. JIT memory processing is untouched.
4. **Generic web Q&A starved** in the agent prompt: a memory-identity
   response instruction (answers not requiring the user's day are one short
   sentence pointing back to their day) plus no public-web routing prefix
   in the agent runtime. Personal retrieval (memories, conversations,
   screen, work context) is unchanged by construction.

Out of scope by design: Send/gift meeting-share, `h.omi.me`, the
meeting-receipt reconciler, Brain Map, a second shell, computer-use,
marketplace, and any capture-gate change (owned by ptt-improvement / #12616).
The Hold/PTT surface is unchanged; its events are only tagged.

## Kill switch

PostHog server-side flags, tri-state fail-closed, following the production
pattern (`utils/jit_rollout.py`): **`exp-002-desktop-identity-v1`** (exposure)
and **`exp-002-desktop-identity-kill-v1`** (revoke). Absent, unknown, or
false ⇒ no enrollment and control chrome. Flag off → paint control, leave
existing assignments in place. No PostHog person/cohort targeting of new
installs (that failed: 215/260 beta installs had a null person-side channel).

## Beta bake vs Stable confirmatory

The Beta roster is a **bug-finding bake**. The stats clock does **not**
start on Beta enrollments: Beta users are self-selected early adopters on a
dev-serving backend, and treating their behavior as confirmatory would
re-import the selection bias the randomization exists to defeat. The
**confirmatory roster is Stable enrollments**, collected after (and only
after) the registry is widened to the stable bundle id — a separate,
explicit decision. Beta enrollments still land in the same Firestore
collection (the desktop-backend data-plane seam pins both channels to the
customer plane), so the bake roster is inspectable, but no readout on it is
promoted to a ship decision.

## Metrics

**Primary (near-term, on the causal path — not retention):**

1. **Day-1 return** after enrollment (a value signal, not
   launch-at-login: an active day means a real conversation or postcard
   interaction).
2. **Teach-rate on shown facts**: `memory_review_action` accept+fix /
   `memory_review_card_shown` — did the postcard's ✓/✗/Fix rows get used?
3. **First grounded bar/PTT success**: the first hold/PTT attempt after
   enrollment ends in a `grounded` outcome (existing PTT lifecycle events,
   now variant-tagged), not `too_short`/`silent_rejected`.

**Secondary (monitored, may fall):** questions asked
(`question_asked` / `question_answered`). The formulation predicts this
*may fall* if silent capturers stay — a fall is not harm by itself; the
primary metrics decide.

**Guardrails:** crash-free sessions by arm (Sentry tags `experiment_id` /
`experiment_variant`), enroll-endpoint failure rate, postcard render
failures.

**Descriptive only:** route mix, daily summary opens, Interject teach
volume. Analysis is intention-to-treat; enrollment is the denominator.

## Analysis

Denominator = `Experiment Enrolled` where
`experiment_id = 'EXP-002-desktop-identity-memory-v1'`, per the
pre-registered roster. HogQL sketch:

```sql
SELECT
  properties.variant AS variant,
  count() AS enrolled
FROM events
WHERE event = 'Experiment Enrolled'
  AND properties.experiment_id = 'EXP-002-desktop-identity-memory-v1'
  AND timestamp >= {confirmatory_start}
GROUP BY variant
```

Outcomes are left-joined onto that roster by `distinct_id` (= uid).
Report absolute percentage-point differences with 95% CIs from two-proportion
tests. No covariate adjustment. **Never condition the analysis on opened
Chat** — Chat-openers are the engaged users; filtering on them re-imports
the latent-engagement confounder inside a design that had solved it. No
subgroup is promoted from exploratory to confirmatory within this id.

## Plane note

The enroll endpoint resolves assignments through the data-plane Firestore
seam (`get_data_plane_firestore_client`), which both the dev desktop-backend
(Beta traffic) and the prod backend pin to the customer data plane
(`based-hardware`, verified in `backend/deploy/runtime_env/*.overlay.yaml`:
`data_plane_project: based-hardware` in dev and prod). If that seam ever
fails to resolve, the endpoint skips enrollment (reason
`assignments_plane_unavailable`) rather than splitting the roster across
planes.

## Tests

- `backend/tests/unit/test_experiments.py` — N-arm draw determinism,
  weights, registry-extension stability, invalid registries, legacy binary
  draw unchanged, arm-name persistence, idempotency, all-arms Enrolled,
  fail-closed persist.
- `backend/tests/routers/test_desktop_experiments.py` — channel/version
  gates, kill-switch-off behavior, plane failure, persist failure,
  idempotent re-enroll, both arms through one endpoint.
- `desktop/macos/Desktop/Tests/DesktopExperimentTests.swift` — enrollment
  policy (Beta-only), forced-variant parsing, fail-closed resolution, owner
  change isolation, Interject arm binding, postcard landing latch.
