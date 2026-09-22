# Mobile presentation experiments

PostHog owns allocation. `ExperimentDefinition<T>` is the client contract for
registered variants, surfaces, namespaces, build eligibility, expiry and optional
server-controlled layers. `MobileExperiments.all` is the bounded registry. These
experiments must never switch memory/task authority, account migration, privacy,
authorization or billing behavior (INV-MEM-5 and INV-CUTOVER-1).

`mobile-summary-feedback-layout-v1` is the first presentation seam: the existing
summary feedback controls are the default; the compact variant uses the same
actions. Its specification is a **draft**, initially targeting `mobile-dev`.
Neither shipping this registry nor generating a plan launches a trial.

## Runtime contract

1. Bootstrap the service with the same public PostHog project token and cloud
   host as analytics. Disable SDK automatic feature-flag events. The dedicated
   provider evaluates the public `/flags/?v=2` endpoint for the settled current
   distinct ID. It rejects HTTP failures, redirects, partial evaluations, quota
   limits and malformed responses. It does not read native cached flag values.
2. Fence with `updateContext(analyticsEnabled: false, ...)` synchronously before
   identify/reset or consent changes. Only re-enable after that SDK operation
   settles for the current generation, using its actual distinct ID. Refresh on
   foreground. The service independently rejects stale asynchronous responses.
3. `open(definition, surface: ...)` waits at most 800ms, shares an in-flight
   request, then returns one sticky lease. A failed request, missing gate,
   unavailable/unknown variant, excluded namespace/build, expired definition or
   unselected layer returns the default **without** assignment or exposure.
4. `mobile-experiments-enabled` must be explicitly `true`. Set it false remotely
   or call `setKillSwitch(true)` locally to revoke active experimental UI and
   attribution. Remote kills are applied when a successful refresh reaches the
   client; they cannot be immediate on disconnected clients.
5. Cache is memory-only, per identity generation, with a five-minute TTL.
   Expired cache never enrolls a new surface or attributes outcomes. Existing
   viewed UI stays stable through transient offline/expiry; explicit revocation
   returns it to the default. Ordinary refreshed variants affect only new leases.
6. Dispose every lease with its caller. Attribution includes only exposed,
   currently held leases, expires with the cache, and never exceeds the 16
   registered keys. Conflicting overlapping variants of one key omit attribution.

A lifecycle transition always invalidates the previous generation, including
A → signed out → A. No persisted assignments survive logout or consent withdrawal.
Diagnostics contain only fixed reason codes and registered keys/surfaces; no HTTP
bodies, user identity, prompts, transcripts, feedback text or arbitrary payloads.

## Tiny features and whole pages

`ExperimentBuilder<T>` accepts a typed variant builder and an explicit loading
builder. It records exposure after a nonempty selected widget paints on the
current route. Its lease survives rebuilds and ordinary flag refreshes. Keep
Navigator, shared providers, controllers and route arguments above this boundary
when replacing an entire page. Both variants must preserve the same action and
navigation contracts. Never render an interactive control as the loading state.

Supply `visible: false` for prefetched pages, offstage tabs and list items outside
the visible viewport; callers own those visibility signals. Route and TickerMode
checks are additional guards. This component does not infer arbitrary ancestor
opacity, clipping, scrolling visibility or a covered native window.

For non-UI/boolean features, register explicit boolean mappings if false truly
means assigned control, then call `lease.expose()` only when the selected behavior
is used. Otherwise a false flag is disabled and has no exposure. For holdouts,
register the exact PostHog `holdout-<id>` key with the default implementation and
include it in `holdoutVariants`; unknown holdout IDs fail safely.

Independent experiments must declare `collision_policy: independent`. For
mutually exclusive trials, set a shared `layer` on definitions and provision a
PostHog multivariate flag `mobile-layer-<layer>` returning exactly one experiment
key. The client does not randomize or choose first-wins allocation. No layer
match means no enrollment. Coordinate layer changes with existing sticky
sessions; a refresh revokes leases whose layer no longer selects their trial.

Debug/test QA overrides require `allowQaOverrides: true`, are unavailable in
release builds, apply only to new leases and produce no assignment/exposure or
outcome attribution. They do not bypass namespace/build/consent/expiry gates.

## Analysis contract

- `experiment_assigned`: authoritative allocation selected for an eligible
  surface, before exposure. Do not use this as the exposed-user denominator.
- `experiment_exposed`: selected UI painted or selected feature was used; once
  per lease. Fields: `experiment_key`, `experiment_version`, `variant`, `surface`,
  `holdout`, `experiment_qa` (false in analysis).
- `$feature_flag_called`: emitted at that same exposure boundary with
  `$feature_flag` and `$feature_flag_response` for PostHog experiment analysis.
- Subsequent outcomes receive `$feature/<registered-key>: <registered-variant>`
  from `outcomeProperties()`. They are bounded to active exposed leases. Async
  journeys should retain this context at journey start and fence it against
  identity/consent changes; an attempt can complete after its widget unmounts.

The adapter explicitly passes `false` for every registered `$feature/<key>` on
all Dart `track` and acknowledged `deliver` calls, then overlays explicit
exposure/outcome properties. This masks native cached flags, including the iOS
SDK's automatic reload after identify. Caller feature values win in pinned
[iOS 3.64.1](https://github.com/PostHog/posthog-ios/blob/3.64.1/PostHog/PostHogSDK.swift)
and the supported Android lower bound
[Android 3.51.0](https://github.com/PostHog/posthog-android/blob/android-v3.51.0/posthog/src/main/java/com/posthog/PostHog.kt).
The adapter snapshots this map before its serialized capture queue.

Automatic product-outcome readers must require `experiment_context_verified ==
true` **and** a string `$feature/<registered-key>` containing a registered
variant. `false` is an explicit absence of attribution, never a control arm.
The manager marks only verified Product Journey Outcome/Product Value context.
Explicit `experiment_exposed` events are the authoritative exposure path.
Native-only SDK events (including identify, set and native autocapture) bypass
the Dart adapter and may still contain native cached flags; those events have
no verified-context marker and must not enter automatic experiment outcomes.
The custom exposure/metric queries use the explicit rendered event and typed
registered outcome events, rather than treating SDK flag properties as exposure.

Aggregate distinct users by exposure, variant and experiment version. Check
sample ratio, assignment-to-exposure drop-off, duplicate exposures, unknown
variants and guardrail completeness before interpreting effects. Exclude local
builds/test identities through the normal analytics eligibility rules. Do not
interpret assignment-only, fallback or QA users as control. Declare conversion
window, primary metric, guardrails, minimum sample and stop rules before launch.

The summary-feedback sample measures successful feedback submissions and uses
`summary_feedback` failure as its guardrail. Both outcomes occur after the
selected controls are exposed, and the journey retains that exposure context.
The guardrail is the share of exposed users with a submission failure within
24 hours, not a failure rate among attempted submissions. Conversation loading
precedes this exposure, so `conversation_load` failures cannot serve as a
guardrail in this funnel. Monitor page-load health separately in the journey
scorecard; this experiment does not establish an effect on conversation utility.

## Prepare an inactive draft

From repository root:

```sh
python3 app/scripts/experiments/provision.py \
  app/docs/experiments/summary-feedback-layout.json --project-id 123
python3 -m unittest discover -s app/scripts/experiments -p 'test_*.py'
```

Replace `123` with the verified intended PostHog project. The default command uses
no credentials or network. It validates operational fields and metric filters
against the analytics registry, then prints a disabled, zero-rollout flag and an
experiment draft with primary/secondary funnel metrics, deterministic metric IDs,
24-hour conversion windows, and a custom rendered-exposure criterion. Guardrails
have a decreasing goal; the primary metric has an increasing goal. The PostHog
funnel engine prepends exposure, so each metric contains its registered outcome
step only. Custom exposure includes the version and excludes QA; the exposure
event carries `$feature/<key>` for native variant attribution.

To create the reviewed inactive draft, an operator may explicitly run:

```sh
# Supply POSTHOG_PERSONAL_API_KEY through the operator's secret environment.
python3 app/scripts/experiments/provision.py \
  app/docs/experiments/summary-feedback-layout.json --project-id 123 \
  --host https://us.posthog.com --apply
```

Use the intended US/EU management host, not the ingest host. The management token
needs feature-flag and experiment read/write scopes and is never an app secret.
The tool does not print it and refuses redirects or pagination outside the
selected host/project. Dry run ignores credentials. No live apply was performed
for this implementation.

Apply discovers all pages of active and archived experiment listings plus flags,
then reconciles by the versioned flag key and an ownership/version marker. Exact
inactive drafts are reused. It never patches an existing object: active,
previously launched, scheduled, archived, foreign-owned or drifted definitions
are refused. Change a reviewed definition using a new key/version rather than
mutating an existing version. If a request fails after flag creation, rerun:
the owned inactive flag is reused and only the missing draft is created. It
verifies both objects after creation and returns IDs plus inactive/draft receipts.
No launch, scheduling, activation, delete or existing-object update endpoint is
available. A concurrent external activation cannot be rolled back by this tool;
read-back fails and requires operator investigation. Unknown event names in the
remote project remain a server validation error; emit approved synthetic staging
fixtures first rather than bypassing that validation.

Before launch: independently check registry/spec parity, the target namespace and
minimum build, expiry, primary/guardrail filters, consent eligibility, layer or
holdout assignments, both visual variants and the kill path. Keep the global gate
disabled until this review is complete. Expiry is enforced locally; operators
also schedule flag retirement, then remove losing variants and the registry entry.

## Verification evidence and limits

Hermetic commands (no real PostHog or Omi endpoint):

```sh
cd app
flutter test --no-pub test/unit/experiments test/widgets/experiments
dart analyze lib/services/experiments lib/widgets/experiments \
  test/unit/experiments test/widgets/experiments
```

The provisioning tests mock HTTP for pagination, exact reuse, interrupted creation,
active/foreign/drift rejection and token-destination safety. Generated metrics and
exposure criteria were additionally checked against PostHog's official query JSON
schema on 2026-09-22. The Dart tests cover assignment/exposure separation, deduplication, identity races,
late responses, timeout/offline defaults, cache expiry, remote and local kills,
consent withdrawal, QA exclusion, server layers, holdouts, boolean control,
malformed/partial API results, full-page variants, navigation and retained input,
hidden surfaces and disposal before assignment. They establish Dart lifecycle and
widget behavior, not installed-device visuals, live ingestion or statistical
readiness. No live experiment is provisioned or launched by these tests.

Protocol references verified against the installed `posthog_flutter` 5.28.0
(lockfile; dependency constraint is ^5.24.0), and official PostHog documentation:
[public flags API](https://posthog.com/docs/api/flags),
[experiment drafts API](https://posthog.com/docs/api/experiments),
[feature flags API](https://posthog.com/docs/api/feature-flags).

Provisioning schema sources:
[metric and exposure definitions](https://github.com/PostHog/posthog/blob/master/frontend/src/queries/schema/schema-general.ts),
[API serializer](https://github.com/PostHog/posthog/blob/master/products/experiments/backend/presentation/serializers.py),
[experiment creation and validation](https://github.com/PostHog/posthog/blob/master/products/experiments/backend/experiment_service.py).
