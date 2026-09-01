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
| Q1: price authority | **Stripe is the authority for price amounts, read live and never copied into the repository.** The catalog owns plan identity and the price-ID -> plan mapping, and deliberately stores no dollar figure. Revised by David on 2026-08-20; see below. |
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

`open_decisions` in the catalog is therefore `{}`, and `--require-publishable` no longer reports B1 or B3.
Since P1 was withdrawn it no longer reports any Stripe import either: `validate_publishable_catalog` now checks
open decisions and cost-accounting completeness only, so **M1 is the sole remaining publishable gap**.

One consequence of the B1 sentinel ruling is load-bearing and easy to get wrong. The rule is narrow and
deliberately so: **retiring the sentinel must not silently reinterpret configuration that is already
deployed.** It says nothing about configuration nobody has deployed.

Only the **Basic** family is bridged, via `_legacy_overlay` in `backend/utils/subscription.py`, which maps a
legacy `0` to unlimited. That is because production actually ships
`BASIC_TIER_WORDS_TRANSCRIBED_LIMIT_PER_MONTH=0` and `BASIC_TIER_INSIGHTS_GAINED_LIMIT_PER_MONTH=0` on the old
meaning; reading those as a finite zero would hand every Free user a zero allowance. The Basic minutes overlay
is bridged too — charts set `300`, so the zero branch is latent, but a deployed `0` there would make
`has_transcription_credits` false for every Free user.

The **chat overlays** (`FREE/NEO/OPERATOR_CHAT_QUESTIONS_PER_MONTH`, `ARCHITECT_CHAT_COST_USD_PER_MONTH`) and
the **Plus transcription overlay** are deliberately **not** bridged: no chart or deploy file sets any of them,
so there is no deployed configuration to protect, and under David's ruling a finite `0` means zero. That is
pinned by `TestChatLimitZeroSemantics` in `backend/tests/unit/test_overage_catalog.py`. If one of those vars is
ever set to `0` in a deploy, bridge it first or the meaning inverts silently.

The catalog's own values always use the typed representation. D2 deletes the overlays and this bridge together.

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

- Desired commercial contract: plan ID, lifecycle, storefronts, currency, interval, entitlements, allocations,
  and exhaustion policy. This is reviewed and versioned in Git. It carries **no price amount** — see the revised
  Q1 above; amounts are read live from Stripe and never copied here.
- Billed identity: the Stripe product/price IDs and the plan each maps to, kept in an append-only recognition
  ledger. This is the one Stripe fact the repository owns, because Stripe cannot supply it.

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

## Q1: amounts live in Stripe, identity lives in the repository

**Revised 2026-08-20 (David).** The original answer here made the repository the system of
record for *intended* price, with Stripe as attested execution state, a prepare/promote
publication workflow, and a reviewed import of existing amounts. That is rejected. No dollar
amount is stored in this repository.

The reasoning is that the drift the original design guarded against only exists if there are
two copies of a price. There is exactly one:

- `backend/routers/payment.py` already calls `stripe.Price.retrieve(...)` and renders
  `unit_amount` directly. The storefront has always shown live Stripe amounts.
- Every dollar figure previously found in the repo was display copy, a code comment, or a
  test fixture -- an unverified duplicate that no test compared against Stripe. Those are the
  duplicates being removed, not replaced with a better-managed duplicate.

So a price change is a Stripe dashboard action and touches no repository file. The
115-files-to-change-a-price problem is dissolved rather than guarded: there is nothing left
in the repo to keep in sync.

### What the catalog still owns, and why it cannot be live

`price_1TAfBB1F8wnoWYvw8XBFM1dX -> architect` is **our** domain knowledge. Stripe does not
know our plan enum, so it cannot answer it. `get_plan_type_from_price_id` needs that mapping
on every webhook and subscription resolution, and an unrecognised price id is precisely what
caused the Apr 17-20 incident: post-revert code recognised neither price, renewals raised
"unknown price ID", and active paying subscribers were dropped to free. Note what that
incident was actually about -- *identity recognition*, not amounts drifting.

The recognition ledger is therefore append-only in Git, where it gets code review, history,
and revert-safety. It is a local dict lookup, so resolving a plan needs no network call and
survives a Stripe outage.

Putting the plan id in Stripe price *metadata* was considered and rejected: it would move
plan identity behind a network call on every webhook, make a metadata typo a
subscriber-affecting bug with no code review, and leave no audit trail.

### Consequences for the rest of this document

- The prepare -> recognize -> validate -> activate -> promote state machine is **deleted**,
  along with `validate_stripe_publication`, `price_spec_digest`, the `publication_state`
  field, the `--bindings` / `--stripe-snapshot` flags, and their tests.
- Work item **P1** (import current Stripe amounts) is **withdrawn** -- there is nothing to
  import. Work item **P2** (publication automation) is **withdrawn**.
- `validate_stripe_price_ids()` at startup becomes the meaningful Stripe check: with amounts
  live, the only thing that can break is a configured price id that does not resolve. It is
  currently existence-only, non-fatal, and skipped in dev -- worth hardening, and that is now
  the whole of the Stripe-side guard.
- The Q4 acceptance guard loses its price-drift half by construction and reduces to
  identity, quota, and entitlement drift, which are still real.

## Q2: policy with the plan, mechanics with the feature

The catalog owns the answer to “what is this plan allowed?”:

- stable identity, aliases, lifecycle, display identity, storefront eligibility, and wire fallback;
- capabilities and named profiles, such as desktop access, cloud vectors, fair-use class, and phone calls;
- per-feature allocations, period, exact unit, finite/unlimited/open-decision state, and exhaustion policy; and
- billed identity: which Stripe price IDs map to this plan (never the amount).

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
| B1: five Free transcription values | **DECIDED (P9/P10): 300 minutes = 18,000s, and the `0 == unlimited` sentinel is retired.** The catalog records the finite value in seconds. Backend defaults derive from it, but existing env overlays remain effective, so no policy changes in this PR. | David selects one value. Generated service/client projections replace Helm, Cloud Run, web, and localization literals; every service reports catalog SHA plus effective value. The publishable guard rejects the open decision and undeclared override. |
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
  production-source Stripe ID inventory, and publishability check. (The offline Stripe binding/snapshot
  validator was deleted with the publication workflow — see the revised Q1.)
- `backend/config/plan_catalog_generated.py` and `backend/config/plan_catalog.py`: generated data plus stable query and
  resolution APIs. Open decisions throw unless a caller explicitly requests preserved legacy behavior.
- Backend migration of the enum, plan sets, display map, default limits, desktop quota profiles, phone-call defaults,
  fair-use membership/defaults, price resolution, support scanning, sync telemetry, and overage predicate.
- A generated temporary wire projection that keeps the released OpenAPI snapshot unchanged until client safety lands.
- Catalog-wide behavioral tests and the local/CI manifest check.

## Fan-out migration plan

Dependencies use the work-item IDs below. “Mechanical” means agents may run the work in parallel after its
dependencies land without changing a decision. “Judgment” means one owner must review the boundary or rollout.

1. **D1 — COMPLETE (2026-08-20).** B1 and B3 were ruled on and applied; `open_decisions` is `{}`. Original scope: update
   `backend/config/plan_catalog.json` only: replace B1's `decision_required` limit and both B3 exhaustion decisions,
   increment `catalog_revision`, regenerate, and update behavioral expectations. Acceptance: `--require-publishable`
   no longer reports B1/B3; no environment, UI, or client value is edited in this item. This blocks D5 quota fan-out,
   but not price import or client decoder work.

2. **P1 — WITHDRAWN (2026-08-20).** Importing Stripe amounts into the catalog is no longer
   part of the design: the repository stores no dollar amounts. See the revised Q1 above.

3. **P2 — WITHDRAWN (2026-08-20).** Publication automation existed to create Stripe prices
   from catalog amounts. With amounts owned by Stripe, prices are created in the Stripe
   dashboard and this workflow has no purpose. Replaced by a much smaller follow-up: harden
   `validate_stripe_price_ids()` so a configured price id that does not resolve fails loudly
   rather than logging, and stop skipping it in dev (which is where B2 lived).

4. **D2 — Generate deployment bindings and effective-config inspection (judgment; depends on D1 for Free quota).** Extend `backend/scripts/generate_plan_catalog.py`; generate one deployment projection consumed by
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
    rules above, and update `.github/agent-docs/plan-catalog.md`, backend/app/desktop guides, and developer API docs.
    Acceptance: an injected eighth source fails CI, while normal non-plan localization/client work does not pay a
    broad scan cost.

P1, C1-C4, and M1 may proceed in parallel. C5-C8 may proceed in parallel after their matching decoder lane. D3a-c may
proceed in parallel after the relevant David ruling. P2, D2, W1, W2, and production binding/floor changes require a
single integration owner because they cross a money or compatibility boundary.

## Open ledger gap — needs verification against dev Stripe

`backend/tests/unit/test_available_plans_resilience.py` labels four IDs "Real Stripe dev price IDs". The
Unlimited pair (`price_1RrxXL…IddzR902`, `price_1RrxXL…3kDbWmjs`) resolves from the recognition ledger. The
**Architect pair does not**:

- `price_1TAznX1F8wnoWYvwyaSVQbZW`
- `price_1TAznX1F8wnoWYvwN8YmzbiC`

If any dev subscriber still bills on those, they land in the skip-write branch: the webhook emits fallback
telemetry and leaves the local row stale. Dev-only, and the asymmetry suggests the Unlimited pair was added to
the ledger and the Architect pair overlooked.

**Deliberately not fixed here.** Appending to the recognition ledger asserts that a Stripe price maps to a plan,
and the only evidence available in-repo is a comment in a test file. That is the same unverified-copy reasoning
this project exists to eliminate — the foundation refused to infer *amounts* from test fixtures, and inferring
*billed identity* from one is worse. Confirm both IDs in the dev Stripe dashboard, then append them.

## Owner decisions still required

1. ~~B1: the canonical Free monthly transcription allowance.~~ **Decided 2026-08-20: 300 minutes (18,000s);
   the ambiguous `0 == unlimited` convention is retired in favour of a typed unlimited.**
2. ~~B3: whether Plus and Unlimited-v2 hard-cap or enter overage.~~ **Decided 2026-08-20: hard-cap; current
   runtime behavior stands and the contradicting second predicate was deleted.**
3. ~~P1 review: approve imported Stripe amounts.~~ **Withdrawn** — no amounts are imported.
   The dev Architect price-id split (B2) is still worth resolving, but it is a configuration
   fix, not a catalog decision.
4. Later release approval: the real client capability/force-upgrade floors and the observation window before deleting
   the remap. These values must come from shipped-build evidence, not this design.
