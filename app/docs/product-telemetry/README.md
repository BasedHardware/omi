# Mobile product telemetry and experiments

Implementation contract for the mobile product feedback stack. Scope approved on 2026-09-22: measurement trust, journey/value/satisfaction instrumentation, an executable agent scorecard, and PostHog experimentation for feature and full-page variants, delivered together in one PR.

## Boundaries

- PostHog owns experiment assignment. The client owns actual feature/page exposure and user-visible outcomes; evaluation or a default value is not exposure.
- Backend owners establish persistence, billing and processing outcomes. Client intent is not a persisted outcome. The existing feedback ledger remains the feedback authority.
- Extend the existing typed event registry with closed journey vocabulary and random attempt correlation. Never send user content, free-form exceptions, phone digits, graph labels or survey comments in product analytics.
- Preserve existing event wire identities. Add distinct outcomes instead of changing historical intent event meanings. Keep the obsolete summary-rating endpoint inert for released clients.
- Scope analytics and experiments to authenticated/anonymous identity and consent epochs. Late asynchronous work cannot be attributed to another account. Capture never depends on analytics succeeding.
- A product attempt has at most one terminal outcome. Pending, cancelled, superseded, unobserved and failed are distinct. A missing event is not proof of failure or churn.
- Query definitions, cohort windows, deduplication and unknown states are versioned and executable. Agent output includes its evidence and uncertainty; it cannot silently change the metric it optimizes.
- Existing UI is the default. Experiment infrastructure supports registered variants, sticky page leases, explicit exposure, kill switches, identity fencing and QA exclusion. No real experiment is launched by repository tests or setup.

## Delivery checklist

- [x] Recoverable SDK initialization, awaited handoff, occurrence time, context isolation and telemetry health.
- [x] Typed correlated journey/progress/outcome/value contract, executable consumers and regression tests.
- [x] Search errors separate from genuine empty results; cancellation intent separate from persistence.
- [x] Recording/transcript/result linkage, capture health and interrupted-background reconciliation.
- [x] Rendered chat/search/conversation outcomes, useful actions and activation signals.
- [x] Intentional summary and recording-quality feedback, release provenance and safe sampling.
- [x] Notification/integration/permission outcomes and route performance observations.
- [x] Versioned agent scorecard, mature retention/churn cohorts, evidence packets and fixture-driven improvement loop.
- [x] PostHog flag provider, registered experiments, feature/full-page builders, lifecycle/identity tests and provisioning dry-run.
- [ ] Integrated independent review, focused tests, local preflight and exact-commit PR/CI verification.

## Feedback population

The prompts use a deterministic 25% target sample and one shared seven-day
per-user cooldown. Eligible conversations with audio are split between summary
and recording questions before widgets mount, so one question cannot starve the
other. Summary feedback is currently limited to the first-party displayed
summary; app-result summaries need explicit result coordinates before their
provenance can be attributed. Recording feedback on the detail page targets the
owned conversation's audio. Explicit recording-session callers use a separate
`target_kind` and ownership lookup.

These prompts are a sparse convenience sample, not a population satisfaction
estimate: recording prompts require completed conversations with available audio.
Nonresponse and missing telemetry remain unknown. Existing chat reason chips and
the authenticated feedback ledger retain richer diagnostic feedback.

## Component guides

- [Experiment runtime, whole-page boundaries and inactive provisioning](../experiments/README.md)
- [Executable scorecard, billing snapshots and agent evidence packets](../../../docs/product-telemetry/README.md)
- [Typed event registry](../../lib/utils/analytics/registry/REGISTRY.md)

## Verification layers

Hermetic source tests and synthetic query fixtures prove implementation semantics. Simulator UI verification proves reachable behavior in the local harness. Ingestion, billing joins, real experiment allocations and device battery/capture behavior require separately identified live evidence. Never present source or fixture output as production observations.


## Validation recorded for this change

The complete Flutter suite passed (2,684 tests; five existing skips), as did all
23 hermetic mobile journeys, the analyzer ratchet, the event registry generator
check and its 11 Python tests, and ten mocked experiment provisioning tests.
Focused identity, delivery, capture, background and experiment tests exercise
failure paths and stale asynchronous work. The combined backend feedback/billing, real-webhook projection and scorecard
suite passed 195 tests; backend typecheck completed with zero errors.

A local iOS simulator build succeeded and the app rendered the welcome and auth
screens against the synthetic local harness. Authenticated simulator acceptance
was blocked by local signing/keychain entitlements; summary/recording feedback
and full-page variants have hermetic widget coverage, not installed-device
acceptance. Local native build configuration changes are excluded from this PR.

No production ingestion, live billing export, real experiment allocation,
physical-device battery/capture qualification or customer uplift was measured.
The scorecard improvement loop is executable with synthetic evidence; it does
not autonomously publish or roll out changes. The experiment draft remains
inactive and its global runtime gate defaults off.
