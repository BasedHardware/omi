# Subscription plan source of truth

Status: architecture decision and foundation implementation. The migration is deliberately incomplete.

Evidence baseline: `origin/main@6cc096a6dc465f0306376b56010f31f9306c61cd`, fetched on 2026-08-20. The task
named `613622b04d` as its base, but the repository-required `make setup` fast-forwarded this worktree to the newer
commit. No intervening subscription, payment, quota, or plan source changed. All repository citations below were
read with `git show origin/main:<path>` at that fetched base. Production values are the owner-supplied, read-only
Cloud Run snapshot from the same date; they are observations, not values selected by this design.

## Decisions

| Question | Decision |
|---|---|
| Q1: price authority | The versioned repository catalog is the system of record for intended subscription price, expressed as integer minor units plus currency and interval. Stripe is provisioned execution state and must carry an attestation to the exact catalog price spec. Existing prices remain explicitly `legacy_external` until a read-only import is reviewed. |
| Q2: entitlements and allocations | Plan policy lives with the plan definition. Feature modules retain meters, counters, enforcement algorithms, and emergency controls, but may not own a second per-plan value or predicate. Units remain typed; they are not coerced into a misleading common number. |
| Q4: acceptance guard | A catalog compiler validates the whole catalog, generates projections, rejects destructive identity/price-ledger changes, inventories committed Stripe IDs, and runs behavioral matrix tests. The final guard admits only catalog readers or byte-for-byte generated projections. Pairwise source regex checks are retired. |
| Q6: identity remap | Do not lower the `99.0.0` floors yet. First ship lossless unknown-plan decoding in every client, then publish the six-value wire schema, set real capability floors, use the existing force-upgrade mechanism for the long tail, observe, and finally delete the remap. Missing or malformed caller identity always receives the oldest safe legacy contract. |

This change does not choose a price. It does now carry David's rulings on the two quota/exhaustion decisions,
taken after this document was first written:

- **B1 — Free monthly transcription allowance is 300 minutes (18,000s)**, the value the listen plane already
  enforces, so no free user loses capability they actually have. The `0 == unlimited` sentinel is retired:
  unlimited is typed `{"kind": "unlimited"}` and `0` means zero.
- **B3 — Plus and Unlimited-v2 hard-cap.** Current runtime behavior stands; the contradicting comment and the
  second `is_overage_plan()` predicate were deleted rather than implemented.

`open_decisions` in the catalog is therefore `{}`, and `--require-publishable` no longer reports B1 or B3. It
still reports the Stripe import (P1) and cost-accounting completeness (M1), which remain genuinely open.

One consequence of the B1 sentinel ruling is load-bearing and easy to get wrong: the *pre-catalog env overlays*
(`BASIC_TIER_*`, `PLUS_TIER_*`, the chat overlays) were authored when `0` meant unlimited, and production sets
the Basic words/insights overlays to exactly `0` on that meaning. Retiring the sentinel must not silently
reinterpret configuration that is already deployed, so those legacy values are read through
`_legacy_overlay_value`, which maps a legacy `0` to unlimited. The catalog's own values use the typed
representation. D2 deletes the overlays and this bridge together.

## Why a repository catalog

The backend enum is the closest existing root, but even it has two shapes: six `PlanType` values and a four-value
`Subscription.plan` schema (`backend/models/users.py`, origin/main lines 82-95 and 129-133). The backend then rebuilds
paid, mobile, and desktop sets (`backend/utils/subscription.py`, lines 28-37), plan cards and price environment keys
(lines 426-494), display names (lines 872-880), and limits (lines 1059-1118). Desktop proactivity is another
independent table (`backend/routers/desktop_proactivity.py`, lines 41-54). This is not an ownership graph; it is a
collection of peers.

Stripe cannot be selected as the intended-price authority merely because it is currently the only place an amount
can be observed. The repository creates subscription Checkout sessions, but its only product/price creation helpers
are `backend/utils/stripe.py` (lines 21-37), whose only production creation caller is the marketplace-app path in
`backend/utils/apps.py` (lines 676-690). No subscription-plan provisioning path exists. The current startup check is
called at import/startup (`backend/main.py`, lines 109-113), skips development and only retrieves IDs
(`backend/utils/subscription.py`, lines 812-837); it neither proves amount nor prevents serving a mismatched revision.

The catalog therefore separates two kinds of fact:

- Desired commercial contract: plan ID, lifecycle, storefronts, price amount in minor units, currency, interval,
  lookup key, entitlements, allocations, and exhaustion policy. This is reviewed and versioned in Git.
- Observed execution object: Stripe product/price ID and its retrieved immutable fields. It is accepted only when a
  protected workflow proves it matches the desired spec and records the binding.

The source file is `backend/config/plan_catalog.json`. `backend/scripts/generate_plan_catalog.py` is its compiler,
and `backend/config/plan_catalog_generated.py` is a generated backend projection. Hand-written Python imports the
stable facade in `backend/config/plan_catalog.py`; it does not parse JSON at process startup.

```text
                            protected, read-only snapshot
                                      from Stripe
                                            |
                                            v
plan_catalog.json --> catalog compiler --> binding/attestation validator
       |                    |
       |                    +--> generated backend identity and policy
       |                    +--> generated client/deploy projections (migration)
       |                    +--> catalog-wide CI compatibility checks
       |
       +--> one query surface: price + entitlements + typed allocations
                               + measurement/cost completeness
```

The generated file is an artifact, never an eighth source. CI compares its complete bytes with compiler output.

## Q1: price publication and failure atomicity

### Current import boundary

Every current paid-plan price is marked `legacy_external`, and each amount is
`{"kind":"external_import_required"}`. This is intentional: no amount was inferred from UI copy, comments, or
test fixtures. `--require-publishable` fails while any price is unimported, any product decision is open, or cost
measurement is incomplete. Until the import work item below is reviewed, Stripe remains the historical evidence for
existing amounts, while the catalog is authoritative that those amounts have not yet been ratified in Git.

Configured environment-variable names are catalog fields during this bridge. Their values remain effective runtime
overlays, which is why B1 is not silently changed by this foundation. The target removes plan price/quota values from
per-service configuration and exposes the effective catalog revision and binding from every serving plane.

### Target price state machine

Additions move in one direction:

1. `legacy_external`: imported identity is recognized, but amount intent has not been ratified.
2. `managed/prepared`: the catalog contains exact amount, currency, interval, lookup key, and spec digest. It is not a
   checkout target.
3. `managed/recognized`: a Stripe Price has been retrieved and attested to that spec; its ID is in the append-only
   recognition ledger. The backend can process its webhooks, but checkout still cannot select it.
4. `managed/purchasable`: the environment's single catalog binding points checkout at the attested Price.
5. `managed/retained`: it is no longer sold, but its ID-to-plan and interval mapping remains forever for renewals,
   cancellation, reconciliation, support, and historical records.

Stripe Price objects are immutable for the commercial fields that matter here; Stripe permits `active` at creation
and later update ([create](https://docs.stripe.com/api/prices/create),
[update](https://docs.stripe.com/api/prices/update)). A protected preparation workflow creates the candidate
inactive, writes metadata `omi_plan_id` and
`omi_price_spec_sha256`, retrieves it, and emits a normalized offline snapshot plus binding. The hermetic validator
requires exact `active`, `livemode`, Product, currency, interval, lookup key, unit amount, metadata, catalog digest,
and a binding for every managed price slot. `prepare` mode requires `active=false`; `publish` mode requires
`active=true`. The binding Price and Product IDs must already be in the catalog's append-only recognition ledger.
The selected environment must match the ledger and the retrieved Price's `livemode`, so a test-mode object cannot
satisfy a production promotion.

There is no honest distributed transaction spanning Git, a deployment, and Stripe. The design instead makes partial
failure non-user-visible:

- Stripe creation/retrieval fails: no binding or checkout pointer changes.
- Catalog validation, review, merge, or deployment fails: the candidate Price is inert/unreferenced and the old
  checkout pointer remains active.
- Stripe activation succeeds but promotion does not: the Price is active but unreachable; this is safe garbage, not
  a customer-visible half-launch.
- Promotion deployment succeeds: only then can checkout return the new ID, after every deployed resolver already
  recognizes it.
- A later Git revert restores the former purchase pointer but cannot remove or remap the new recognition entry.

That last rule is the Apr 17-20 acceptance case. On `origin/main`, the incident is documented directly in the old map:
a separately created Neo product survived a code revert, and post-revert renewals became unknown
(`backend/utils/subscription.py`, lines 497-514). Under this design the preparation PR would have added both Neo prices to
the recognition ledger before exposure. The compatibility check rejects deleting or remapping them, so reverting
the purchasable pointer cannot downgrade their subscribers to Free.

Live Stripe access does not belong in ordinary CI. CI validates catalog structure, compatibility, and fixture-backed
publication behavior. The protected publish workflow obtains the live snapshot with narrowly scoped credentials and
validates the exact merged/deployed SHA before promotion.

## Q2: policy with the plan, mechanics with the feature

The catalog owns the answer to “what is this plan allowed?”:

- stable identity, aliases, lifecycle, display identity, storefront eligibility, and wire fallback;
- capabilities and named profiles, such as desktop access, cloud vectors, fair-use class, and phone calls;
- per-feature allocations, period, exact unit, finite/unlimited/open-decision state, and exhaustion policy; and
- intended customer price and its Stripe binding state.

Feature modules own how those declarations are measured and enforced: Redis/Firestore key shape, counter updates,
request admission, overage arithmetic, provider selection, kill switches, and anti-abuse algorithms. A feature may
consume an operational emergency override only when the catalog declares that overlay, its effective value is
inspectable, and its use emits the shared fallback telemetry. An overlay cannot invent a new plan or undeclared
entitlement. The end state has no silent per-service quota override.

Units remain a tagged contract. Operator chat is a count of `question`; Architect chat is integer `usd_cent`.
Converting both to a float would erase the enforcement contract and reproduce the current split between
`chat_questions_per_month` and `chat_cost_usd_per_month` (`backend/models/users.py`, lines 103-115). Money is stored as
integer minor units in the catalog and converted only at an existing wire boundary that still requires dollars.

“What does it cost us?” has two parts:

- Included economic policy belongs in the plan allocation. Architect's catalog entry therefore carries 40,000
  `usd_cent`, while question-based plans retain question counts.
- Realized provider cost is runtime telemetry, not a static catalog value. `measurement_contracts` names the usage
  and cost source and states whether coverage is complete, partial, or missing. Today chat cost is explicitly partial:
  the monthly reader says backend GPT/Gemini chat has no cost field (`backend/database/user_usage.py`, lines 53-64). The
  other cataloged features explicitly report missing cost attribution rather than pretending zero cost.

A catalog query can consequently return the entire policy row and the measurement contract. The migration is not
complete until each required cost contract is `complete`; the compiler's publishability mode enforces that target.

Localized prose remains localization data. The catalog owns message identity and typed interpolation values; it does
not become an English string table copied into 98 ARB files. Clients render generated values through their normal
localization machinery.

## Q4: catalog-wide acceptance and guard economics

The permanent acceptance contract is:

1. Validate the complete catalog schema and references. Reject floats, ambiguous environment ownership, unknown
   profile/unit/state values, incomplete managed price specs, free-plan Stripe mappings, and malformed identifiers.
2. Compile every checked-in projection deterministically and compare complete bytes. A manually edited generated
   artifact fails.
3. Compare the catalog with the merge base. Plan IDs cannot disappear; wire aliases and every recognized Stripe
   price/product mapping are append-only and cannot be remapped; any catalog change increments its revision.
4. Scan production source/config for committed `price_*` and `prod_*` literals. Every one must be represented by the
   catalog. Tests, fixtures, generated artifacts, and prose are excluded from that identity inventory.
5. Run behavioral matrices over every catalog plan: identity, paid/storefront membership, allocations and units,
   exhaustion, retained price resolution, publication failure states, and wire projection.
6. At the end of migration, require every deployed consumer to be registered as either a direct catalog reader or a
   deterministic generated projection. No “keep in sync” consumer is admissible.

The check is registered as `plan-catalog-contract` in `.github/checks-manifest.yaml` for local and CI lanes. It is
defined over the catalog and its consumer boundary, not symbol pairs. The previous check demonstrates why: it parsed
only `LEGACY_PRICE_MAP` and `DEFAULT_PRICE_TO_PLAN` (`backend/tests/unit/test_stripe_webhook_behavioral.py`, lines 310-345),
while the unchecked `PAID_PLANS` immediately beside the latter omitted two paid plans
(`backend/scripts/support/find_stripe_entitlement_mismatches.py`, lines 30-59). The support scanner now imports generated
catalog mappings instead of maintaining either copy.

This foundation enforces items 1-5 now for the backend projection and scans every supported production source/config
extension for uncataloged Stripe IDs. Item 6 is deliberately a migration completion condition: until G1 lands the
remaining client and deployment value mirrors are known debt, so this branch must not be described as fully
consolidated. The broad trigger is the temporary cost of making a newly committed eighth identity source fail during
that interval.

Guard withdrawal is explicit:

- Schema, deterministic compilation, behavioral matrices, and append-only billed-identity compatibility are
  permanent product contracts. They are replaced only by an equivalent compiler/type boundary, never deleted because
  they have been green for a long time.
- The broad legacy-source trigger/inventory is transitional. Withdraw it only when the consumer registry contains
  zero manual mirrors, all plan literals outside tests/docs are generated or read from the catalog, and a test proves
  adding an unregistered consumer fails. The withdrawal PR deletes the legacy allowlist and its fixtures together.
- The committed Stripe-ID source scan may be withdrawn after deployment bindings are generated exclusively from the
  catalog and the runtime-image/source-closure check proves no other config can carry IDs. Its replacement is that
  structural boundary plus the append-only ledger check.
- Byte comparison for a checked-in generated projection is withdrawn if that projection becomes build-only. The same
  PR must add the build step and retain compiler tests. This is substitution, not guard erosion.

These conditions make the temporary guard pay for migration and then disappear; they do not leave a permanent
source-scraping tax after compiler ownership is complete.

## Q6: retire the identity remap in order

There are currently two different capability decisions. Catalog shape uses real client floors, but desktop callers
with missing or malformed versions fail open while mobile fails closed (`backend/utils/subscription.py`, lines 600-657).
Plan identity uses unset `99.0.0` defaults and fails closed for every missing/unknown caller
(`backend/utils/subscription.py`, lines 660-690). The consolidated rule is:

> If platform, version/build, or capability evidence is absent, unknown, or malformed, serialize the oldest lossless
> legacy contract. Never infer capability from absence.

Web may be declared always-current only at its controlled server-rendered boundary; an arbitrary caller saying
`platform=web` is not proof for other endpoints.

Retirement sequence:

1. Keep the remap and the generated four-value `LEGACY_WIRE_PLAN_VALUES` projection. The canonical `PlanType` already
   has all six values, but the released schema remains narrow for now.
2. Ship a lossless unknown-plan fallback in macOS, Windows, Flutter, and web. “Unknown” must preserve the raw string,
   render safe neutral copy, deny unrecognized paid capability, and never silently convert persisted identity to
   `basic`. Flutter's current parser maps an unknown string to Basic (`app/lib/models/subscription.dart`, lines 33-38);
   macOS has neither Plus/Unlimited-v2 nor an unknown case
   (`desktop/macos/Desktop/Sources/Services/APIClient/APIClient+Settings.swift`, lines 365-371).
3. Add behavioral decode fixtures for all six known values plus a future value in every client. Release those builds.
4. Replace the two functions with one catalog capability matrix and use it on every plan-bearing response, including
   upgrade responses and 402 details. The generated app-client OpenAPI contract then exposes the complete enum; do
   not bypass its directional compatibility check.
5. Set real per-platform capability floors to the first released tolerant builds. Missing/invalid callers continue to
   get the legacy projection.
6. After adoption evidence is sufficient, raise `MINIMUM_SUPPORTED_BUILDS` for the unsupported long tail. The existing
   configuration starts at zero (`backend/config/account_cutover.py`, lines 18-27) and already emits `force_upgrade`
   at the access boundary (`backend/utils/account_cutover/access.py`, lines 143-177). This is a deliberate release
   decision, not a
   catalog compiler side effect.
7. Observe raw six-value responses with no decode failures, then remove the identity remap, its `99.0.0` variables,
   and the temporary four-value schema projection. Unknown-value client handling remains permanently.

## B1-B6 resolution

| Finding | Foundation now | Target resolution |
|---|---|---|
| B1: five Free transcription values | The catalog records B1 as `decision_required`, in seconds, with legacy runtime value zero and all five observations. Backend defaults derive from it, but existing env overlays remain effective, so no policy changes in this PR. | David selects one value. Generated service/client projections replace Helm, Cloud Run, web, and localization literals; every service reports catalog SHA plus effective value. The publishable guard rejects the open decision and undeclared override. |
| B2: split dev Architect IDs | Both monthly IDs and the shared annual ID are in the append-only ledger and resolve to Architect without a live Stripe lookup, so either service's existing subscriber remains recognized. | Read-only import verifies both objects. One environment binding becomes purchasable; the other becomes retained. All services consume the same generated binding, making a split impossible. |
| B3: two overage predicates and false prose | `enforce_chat_quota` and `utils.overage.is_overage_plan` now call one catalog predicate. Plus/Unlimited-v2 retain hard-cap behavior through explicit open decision B3. | David selects `hard_cap` or `overage` once in the catalog. Enforcement, reporting, UI, and billing projections derive from that field and its typed unit. |
| B4: paid plans disappear | Paid-plan IDs and telemetry allowlists are generated; the support scanner and sync rate-limit telemetry consume them. Plus and Unlimited-v2 have behavioral coverage. | Remaining consumers may use only the generated set. The consumer registry rejects a new manual predicate. |
| B5: six identities, four-value wire, throwing client | Six canonical values and the `pro` alias are generated from the catalog. The four-value released wire projection is also generated, so it is a visible compatibility state rather than a second enum. | Ship unknown fallbacks, expose six values across every endpoint/schema, set real floors, force-upgrade the long tail, then delete the projection and remap in the sequence above. |
| B6: active prices called legacy | IDs are called retained/recognized, not historical, and all supplied live production IDs remain mapped. Compatibility tests prohibit deletion or remapping. | Read-only Stripe import attaches exact specs and environment bindings. Sale status is independent from recognition, so an actively sold or retired Price always resolves. |

The production snapshot also says `STRIPE_PRO_*` aliases the Architect IDs and `STRIPE_NEO_*` remains configured.
Those are represented as accepted environment aliases of the same catalog plans; aliases never create another plan.
The repository already demonstrates the live/repo Free divergence: production charts set 300 minutes
(`backend/charts/backend-listen/prod_omi_backend_listen_values.yaml`, lines 326-327, and
`backend/charts/pusher/prod_omi_pusher_values.yaml`, lines 301-302), while development uses 1,000,000
(`backend/charts/backend-listen/dev_omi_backend_listen_values.yaml`, lines 326-327, and
`backend/charts/pusher/dev_omi_pusher_values.yaml`, lines 282-283). The owner-supplied Cloud Run value of 600 is therefore
treated as an observed overlay, not a catalog answer.

## Foundation delivered here

- `backend/config/plan_catalog.json`: canonical six-plan identity, aliases, lifecycle, storefronts, typed allocations,
  profiles, open decisions, measurement completeness, billing intent state, recognized prices, and products.
- `backend/scripts/generate_plan_catalog.py`: strict schema/compiler, deterministic projection, merge-base compatibility,
  production-source Stripe ID inventory, publishability check, and offline Stripe binding/snapshot validator.
- `backend/config/plan_catalog_generated.py` and `backend/config/plan_catalog.py`: generated data plus stable query and
  resolution APIs. Open decisions throw unless a caller explicitly requests preserved legacy behavior.
- Backend migration of the enum, plan sets, display map, default limits, desktop quota profiles, phone-call defaults,
  fair-use membership/defaults, price resolution, support scanning, sync telemetry, and overage predicate.
- A generated temporary wire projection that keeps the released OpenAPI snapshot unchanged until client safety lands.
- Catalog-wide behavioral tests and the local/CI manifest check.

## Fan-out migration plan

Dependencies use the work-item IDs below. “Mechanical” means agents may run the work in parallel after its
dependencies land without changing a decision. “Judgment” means one owner must review the boundary or rollout.

1. **D1 — Rule on B1 and B3 (judgment; no code until David answers).** Update
   `backend/config/plan_catalog.json` only: replace B1's `decision_required` limit and both B3 exhaustion decisions,
   increment `catalog_revision`, regenerate, and update behavioral expectations. Acceptance: `--require-publishable`
   no longer reports B1/B3; no environment, UI, or client value is edited in this item. This blocks D5 quota fan-out,
   but not price import or client decoder work.

2. **P1 — Import current Stripe facts read-only (judgment, parallel with C1-C4; no Stripe mutation).** Inspect every
   cataloged price/product in dev and prod. Update each `billing.prices[]` amount, currency, interval, lookup key, and
   binding state in `backend/config/plan_catalog.json`; add any discovered billed ID to the recognition ledger. Add
   redacted immutable fixtures under proposed path backend/tests/fixtures/plan_catalog/stripe/ containing only object IDs and
   validated non-secret fields. Acceptance: every chart/Cloud Run ID appears exactly once with the same plan+interval;
   the two B2 monthly IDs both resolve; active B6 IDs are not classified by age; David approves the imported customer
   amounts. Do not activate, archive, or create anything. Depends on foundation only.

3. **P2 — Build protected prepare/promote automation (judgment, risky; depends on P1).** Add the proposed files
   backend/scripts/prepare_subscription_prices.py, backend/scripts/validate_subscription_price_promotion.py, and
   .github/workflows/subscription_plan_price_publish.yml; extend the catalog with explicit prepared/active bindings.
   The workflow takes an exact main SHA and environment, creates only unreachable candidate Prices, writes metadata,
   retrieves them, and emits a binding/snapshot artifact. Promotion validates the deployed catalog SHA before changing
   the single purchase pointer. Acceptance: hermetic fixtures prove every failure state above and the Apr 17-20
   create→expose→revert scenario; normal CI has no Stripe credentials; production requires environment approval. No
   live workflow run belongs in the implementation PR.

4. **D2 — Generate deployment bindings and effective-config inspection (judgment; depends on P1, and D1 for Free
   quota).** Extend `backend/scripts/generate_plan_catalog.py`; generate one deployment projection consumed by
   `backend/charts/backend-listen/{dev,prod}_omi_backend_listen_values.yaml`,
   `backend/charts/pusher/{dev,prod}_omi_pusher_values.yaml`, `backend/deploy/runtime_env/`,
   `backend/deploy/runtime_env.yaml`, and `config/deployment-setting-classification.json`. Remove hand-authored plan
   price/quota env values only after their generated replacements are live. Add a read-only internal diagnostic or
   startup structured event containing catalog revision/SHA, environment binding IDs, and effective overlays.
   Acceptance: rendering every service from the same environment yields one binding and one quota value; a deliberate
   mismatch fails preflight; `desktop-backend` remains correctly plan-config-free unless it becomes a consumer.

5. **D3 — Finish backend policy consumption (mostly mechanical, parallel sub-lanes; depends on D1 where noted).**

   - D3a chat: `backend/utils/subscription.py`, `backend/utils/overage.py`, `backend/routers/chat.py`, and
     `backend/routers/payment.py`. Remove remaining per-plan caps/copy branches and dollar/question predicates.
     Depends on D1 for B3. Acceptance: every plan×unit×exhaustion case comes from the catalog; reporting and admission
     cannot disagree.
   - D3b transcription/fair use: `backend/utils/subscription.py`, `backend/utils/fair_use.py`, listen/sync admission,
     and their tests. Depends on D1 for B1. Acceptance: plan selection and defaults contain no manual plan table;
     operational anti-abuse switches remain feature-owned and cannot change a plan entitlement silently.
   - D3c desktop/phone: `backend/routers/desktop_proactivity.py`, `backend/database/phone_call_config.py`, and
     `backend/utils/phone_calls.py`. Acceptance: Firestore overrides are surfaced as declared effective overlays with
     telemetry; defaults and plan membership are catalog-only.

6. **M1 — Complete cost attribution (judgment, parallel with client work; depends on the Q2 measurement contract).**
   Update `backend/database/llm_usage.py`, `backend/database/user_usage.py`, backend/desktop chat writers,
   transcription analytics, and conversation-processing usage writers. Change `measurement_contracts` only when a
   behavioral test proves coverage. Acceptance: a per-plan report joins realized usage/cost to the catalog without
   invented zeros; every required `cost_status` is `complete`; provider/BYOK exclusions are explicit. This is not a
   reason to normalize question caps into dollars.

7. **C1-C4 — Ship lossless unknown-plan decoding (bounded judgment, safe to parallelize by client; foundation only).**

   - C1 macOS: `desktop/macos/Desktop/Sources/Services/APIClient/APIClient+Settings.swift` and focused decoding/UI
     tests. Add Plus and Unlimited-v2 plus an unknown raw-value representation.
   - C2 Windows: `desktop/windows/src/renderer/src/lib/omiApi.generated.ts`, shared billing types/parsers, and renderer
     tests. Generated unions must be wrapped by a tolerant runtime parser.
   - C3 Flutter: `app/lib/models/subscription.dart`, generated subscription wire models, and model/provider tests.
     Replace unknown→Basic with a lossless unknown representation and neutral capability behavior.
   - C4 web: `web/app/src/types/user.ts`, `web/app/src/lib/api.ts`, settings plan components, and tests. Unknown values
     render neutral copy and never grant capability.

   Acceptance for every lane: fixtures decode all six catalog IDs, `pro`, and `future_plan_123`; the future value does
   not throw, is not rewritten to Basic, preserves its raw identity through re-encoding where applicable, and grants
   no paid feature by assumption. Record the first released tolerant build for Q6.

8. **C5-C8 — Replace client plan facts with generated projections (mechanical after C1-C4; parallel by client).**

   - C5 macOS removes value/copy fallbacks from
     `SettingsContentView+BillingHelpers.swift` and consumes generated identity/allocation DTOs.
   - C6 Windows removes `PLAN_FALLBACKS` from `desktop/windows/src/renderer/src/lib/billing.ts`; this also eliminates
     the existing 200-question subtitle/100-question description contradiction at lines 349-358 without choosing a
     new policy value.
   - C7 Flutter updates `app/lib/utils/plan_pricing.dart`, settings plan/usage widgets, and ARB templates so numeric
     interpolation comes from catalog responses while translations remain local.
   - C8 web/admin updates settings displays and replaces `web/admin/lib/stripe-subscriptions.ts` (lines 41-48) product literals
     with the generated product projection.

   Acceptance: changing a catalog fixture updates every projection through one generator run; hand-editing a
   projection fails; no client contains a numeric plan allocation, product ID, or membership predicate outside
   generated/test/localization scaffolding.

9. **W1 — Consolidate the capability/wire contract (judgment; depends on C1-C4 released builds).** Replace
   `should_show_new_plans` and `client_understands_plus_unlimited_v2` with one catalog-driven capability evaluator in
   `backend/utils/subscription.py`; thread it through `backend/routers/users.py`, `backend/routers/payment.py`, and 402
   detail construction. Remove the inline four-value schema only after the app-client OpenAPI compatibility check
   accepts the released decoder baseline. Acceptance: a platform/version/missing/malformed matrix proves the single
   fail-closed rule and every plan-bearing endpoint uses the same serializer.

10. **W2 — Lower floors, drain the long tail, and delete remap (judgment, risky; depends on W1 and release evidence).**
    Put the first tolerant build for each platform into the unified capability table. Observe decode/error telemetry;
    then, with explicit release approval, set nonzero `MINIMUM_SUPPORTED_BUILDS` for unsupported clients. After the
    adoption window, delete `PLUS_UNLIMITED_V2_MIN_*`, `wire_plan_for_client`, and
    `LEGACY_WIRE_PLAN_VALUES`. Acceptance: all six values travel unchanged through subscription, upgrade, webhook,
    quota-402, support, and client round-trip tests; missing callers still receive a defined legacy/upgrade response.

11. **G1 — Close the transitional guard (mechanical cleanup; depends on D2, D3, C5-C8, W2).** Add the final consumer
    registry, prove it contains zero manual mirrors, remove legacy source triggers/allowlists under the withdrawal
    rules above, and update `docs/agents/plan-catalog.md`, backend/app/desktop guides, and developer API docs.
    Acceptance: an injected eighth source fails CI, while normal non-plan localization/client work does not pay a
    broad scan cost.

P1, C1-C4, and M1 may proceed in parallel. C5-C8 may proceed in parallel after their matching decoder lane. D3a-c may
proceed in parallel after the relevant David ruling. P2, D2, W1, W2, and production binding/floor changes require a
single integration owner because they cross a money or compatibility boundary.

## Owner decisions still required

1. B1: the canonical Free monthly transcription allowance, expressed in seconds, including whether zero means
   unlimited or whether the ambiguous zero convention is retired.
2. B3: whether Plus and Unlimited-v2 hard-cap or enter overage after their included chat allowance. The current runtime
   behavior remains hard-cap until this is answered.
3. P1 review: approve the exact imported Stripe amounts and which of the two dev Architect monthly Prices becomes the
   single purchasable binding. The non-selected ID remains recognized.
4. Later release approval: the real client capability/force-upgrade floors and the observation window before deleting
   the remap. These values must come from shipped-build evidence, not this design.
