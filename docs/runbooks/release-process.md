# Release & Deployment Process

Internal maintainer doc — lean release engineering: build once, promote
immutable digests through beta to prod, roll back by deploying an older
release. Tracking issue: https://github.com/BasedHardware/omi/issues/10049

## Philosophy: lean but high value

Omi is built and operated by a very small team. Release infrastructure is
therefore optimized for **low devops, hard-to-break beta/prod, easy deploys,
and few footguns** — in that priority order. A small system we finish, trust,
and exercise daily beats an elaborate one that is half-built. When choosing
between a bespoke mechanism and a native platform control (GitHub environment
protection, Cloud Run revisions and traffic splitting, Helm revisions, GCS
object versioning), choose the platform control.

## The seven rules

1. **Build once, promote digests.** Every merge to `main` builds service
   images once. Beta and prod deploy the exact same `repository@sha256:...`
   digests — prod never rebuilds, re-resolves a branch, or deploys a mutable
   tag. Tags are human-readable labels, never deployment authority. No `main`
   SHA deploys directly to prod; only a beta-soaked record is prod-eligible.
   (If builds are ever made incremental, unchanged-component digests may be
   composed from the prior record only via a content hash of the component's
   full input tree — never path filters, which silently ship stale code.)
2. **Promote artifacts, not branches.** There are no `beta`/`prod` branches
   and no sync bots. What is deployed where is recorded in release records and
   the GitHub environment audit log, not in branch topology.
3. **Deploy and rollback are the same command.** Rolling back means deploying
   an older release record through the identical code path. Because rollback
   shares every line with deploy, it is exercised on every release and cannot
   rot into an incident-day surprise. Never build a separate rollback system.
4. **Pin everything a release depends on.** Image digests, Secret Manager
   secret *versions* (never `latest`), and rendered config/values. Nothing
   about a running release may drift without a new release.
5. **Beta is a ring, not a lab.** Beta-channel users are real users on the
   shared production data stores, served by beta instances of the stateless
   services running one release ahead of prod. Real beta traffic is the
   acceptance signal; synthetic checks stay cheap (auth + one streaming
   round-trip smoke test against a no-traffic revision).
6. **Never remove a deploy path before its replacement has shipped for
   real.** Old paths are deleted one at a time, only after the new path has
   handled actual production releases.
7. **Enforcement grows by ratchet.** Add a CI check for a release rule after
   the rule is actually violated, not speculatively (same philosophy as
   testing — see `AGENTS.md`).

## Release records

On every merge to `main`, after images build and push, CI writes an immutable
JSON record to a versioned, retention-locked GCS bucket:

```jsonc
// gs://omi-releases/records/<release_id>.json
{
  "release_id": "2026-07-20.1",   // date.seq — human-readable, sortable
  "git_sha": "…",
  "eligibility_run_id": "…",      // CI run that built and tested this release
  "images": { "backend": "gcr.io/...@sha256:…", "pusher": "…" },
  "rendered_config": { "beta/backend-listen": "gs://…/config/<id>/beta/backend-listen.yaml#sha256:…" },
  "secret_versions": { "OPENAI_API_KEY": "projects/…/versions/42" },
  "topology": { "beta": { "cloud_run_services": { "backend": "backend-beta" } } },
  "created_at": "…"
}
```

**A record must be deployable, not merely verifiable** — store rendered
values/config as immutable objects referenced with hashes, never hashes alone
(a hash can prove identity but cannot restore anything).

The record is the only input a prod-capable deploy accepts — no free-form SHA,
branch, tag, image, or Helm revision. Grow the schema only when a deploy
actually needs a new field.

Ring state is three GCS object shapes — still no service, no database:

- `records/<release_id>.json` — immutable deployable inputs (above).
- `rings/<ring>/active.json` — current serving record, previous verified
  record, and hold/quarantine flag; written with `ifGenerationMatch`
  compare-and-swap. (Deploy serialization itself is a GitHub Actions
  `concurrency: deploy-<ring>` group — the CAS is a backstop, not a lock
  service.)
- `receipts/<ring>/<release_id>/<run>.json` — append-only record of what
  actually happened: Cloud Run revisions/traffic, Helm revisions,
  verification and restore results. Receipts are a write-only audit trail;
  never build a reconciler on top of them.

## Rings

```text
main merge ──► build once ──► release record
                                  ├─► dev    — auto
                                  ├─► beta   — auto: newest record → beta lane
                                  └─► prod   — manual: deploy prod <release_id>
                                               (GitHub environment gate, same digests)
```

- **dev** — development auto-deploys, unchanged.
- **beta** — beta instances of the stateless services (backend,
  backend-listen, pusher, llm-gateway, agent-proxy) at beta endpoints
  (`api-beta.omi.me`), serving real beta-channel desktop/mobile clients.
  Shares production data stores. A service joins the ring system only once
  it has a declared recovery class and a tested ring strategy; until then it
  keeps its dedicated deploy path.
- **prod** — deploys a beta-soaked record behind the GitHub `prod` environment
  gate. The gate is only a barrier when paired with: a prod-only OIDC identity
  bound to repo + environment, explicit workflow/ref guards, and code
  ownership + required checks on `.github/workflows/` — otherwise any future
  merged workflow can request the environment and reduce prod safety to one
  approval click. Promotion criteria: the record served beta for at least the
  soak window (default: overnight) with no new Sentry crash groups,
  fallback/error rates in bounds, **and** a minimum exposure floor (active
  sessions, streamed minutes) — a quiet night must not qualify a release.

Per-ring configuration lives in source-controlled values and
`backend/deploy/release_rings.yaml`; the record writer materializes and hashes
the beta/prod objects before they can be deployed. It captures each ring's
public ConfigMap at record-build time, turns every Cloud Run `env_var` into a literal,
pins Cloud Run and ExternalSecret numeric versions, and writes a materialized
`beta` runtime lane into the record. The beta renderer changes only stateless
identities and endpoints. It intentionally preserves existing GPU endpoints,
which is the explicit #10057 boundary.

## Implemented workflow contract

- `release-record.yml` runs only after a successful `Release Eligibility` run
  for the current `main` tip. It builds backend, pusher, llm-gateway, and
  agent-proxy once, records their OCI digests (backend-listen uses the backend
  digest), resolves every Secret Manager reference to a numeric version, and
  writes create-only config and record objects.
- `deploy-release-ring.yml` accepts only `ring` and `release_id`. It uses the
  selected GitHub environment and that environment's OIDC identity; it has no
  SHA, tag, branch, Helm-revision, or image input. `prod` additionally requires
  the literal `confirm=deploy-prod` after the GitHub environment approval. The
  workflow controller stays pinned to the dispatch commit; only immutable chart
  source inputs are checked out from the record's full Git SHA.
- Before mutation, a ring deploy server-dry-runs the recorded ConfigMap and all
  rendered Helm resources. It then captures Cloud Run traffic, the public
  ConfigMap, deployed Helm revisions plus manifest digests, and the active
  pointer generation. It writes a `started` receipt, creates no-traffic Cloud Run revisions using the
  recorded public config and numeric secret versions, performs an authenticated
  health smoke, and for beta proves an authenticated known-audio transcription
  through the tagged candidate before applying the recorded
  ConfigMap/ExternalSecret/Helm values by digest and switching traffic. Prod
  depends on that verified beta evidence plus the soak, because prod has no
  public candidate URL. A deterministic failure restores the snapshot once,
  removes the failed candidate's tagged route, deletes resources that did not
  exist before a bootstrap attempt, refreshes restored ExternalSecrets, and
  verifies observed Cloud Run traffic, ConfigMap content, and Helm manifests.
  It also restores the pre-mutation active pointer if a later evidence write
  failed after pointer advancement. Any failure to converge writes
  `partial_mutation`, holds the record, and invokes the configured pager webhook.
- `prod` additionally requires a verified beta receipt older than the configured
  soak window (12 hours by default) and refuses a beta-held record. The prod
  environment approval is where the operator records the initial Sentry,
  fallback/error-rate, and exposure-floor review; automate those predicates
  only after they have a proven query contract.
- iOS TestFlight and Android internal builds carry a non-user-controlled beta
  build identity and always use `api-beta.omi.me`. macOS beta uses that Python
  API too. Its Rust desktop-backend keeps the signed production endpoint and
  the separate `desktop_promote_prod.yml` roll-forward-only recovery class;
  it is deliberately not claimed as a v1 release-ring workload.

Before enabling either workflow, provision the `beta` and `prod` GitHub
environments, a retention-locked/versioned `RELEASE_RECORDS_BUCKET`, and two
least-privilege Workload Identity bindings. The prod binding must restrict
claims to this repository **and** the `prod` environment; the record writer
may read the production public ConfigMap and write records/config only, and the
ring deployer may read records plus mutate only its own ring. It also needs
read access to the existing, narrowly scoped `RELEASE_SECRET` used only to mint
the beta candidate's short-lived probe identity. Before the first
beta deploy, provision the beta Cloud Run service identities, namespace,
public ConfigMap with beta Cloud Tasks targets, ExternalSecret Workload Identity,
static ingress addresses/certificate, and DNS
for `api-beta.omi.me`, `pusher-beta.omi.me`, and `agent-beta.omi.me`; the
workflow fails closed if any prerequisite is absent. Protect `main` so the
recursive `.github/workflows/**` CODEOWNERS rule and the `release-ring-guards`
check are required. These are control-plane settings, not values to place in
this repository.

## Deploying and rolling back

`deploy <ring> <release_id>`:

1. Resolve the record from the bucket; refuse anything else.
2. Dry-run every recorded GKE render, then snapshot the ring's active serving
   state and active-pointer generation before any mutation.
3. Cloud Run: create no-traffic revisions from recorded digests → smoke check
   the revision URL → shift traffic.
4. GKE: apply charts with recorded digests and values and wait for rollout.
5. On deterministic failure before or immediately after the traffic switch:
   restore the pre-mutation snapshot automatically (Cloud Run: shift traffic
   back, remove the candidate tag, and delete a first-time service; GKE:
   restore the ConfigMap and backend-secrets, roll back existing Helm releases,
   and uninstall first-time releases). Every restore target is read back and
   compared with the snapshot before recovery is accepted. If restoration also fails, write
   `partial_mutation` with the exact component diff, leave state visible, and
   page — no recursive recovery attempts.
6. A failed record is marked held in `rings/<ring>/active.json` so auto-deploy
   does not retry the same bad candidate.

Later SLO degradation pages a human and offers the one-command rollback —
never automatic (that is the flapping trap).

**Rollback = the same command with an older `release_id`.** The only separate
emergency path is traffic-only: shifting Cloud Run traffic to a previous
healthy revision. It cannot build images or change config.

For today's manual prod deploy and traffic-repair procedures, see
`docs/doc/developer/backend/prod_hotfix_runbook.mdx` and
`docs/runbooks/backend-deploy-rollout-safety.md`.

## Recovery class per surface

Every promotable surface declares exactly one recovery class. A surface with
no declared class is not promotable, and **a class may be declared only for a
tested mechanism** — an untested restore path is a rollback that works on
paper.

| Surface | Class | Mechanism |
|---|---|---|
| Cloud Run services | `exact_restore` | Deploy older record (digests + traffic map). |
| GKE/Helm services | `exact_restore` | Deploy older record (digests + values). |
| Runtime config / secrets | `exact_restore` | Older record's config + pinned secret versions. |
| Web/CDN | `pointer_restore` | Versioned asset pointer + cache invalidation. |
| macOS channels | `roll_forward_only` | Update feeds choose the newest release and promotion is roll-forward only (`desktop_promote_prod.yml`): halt rollout, restore server-side compatibility, ship a higher-version hotfix. Upgrades to `pointer_restore` only when a tested channel-pointer rollback path lands. |
| Mobile stores | `roll_forward_only` | Halt rollout; ship compatible higher-version hotfix. |
| Schema/data | `roll_forward_only` | Expand/contract + compensating migration; no blind data rollback. |
| Firmware | `roll_forward_only` | Stop rollout; signed recovery image. |

## Compatibility rules

Because beta and prod rings share live data stores, these are load-bearing:

- Schema/data changes follow **expand → dual read/write → backfill →
  contract**, never destructive in the same release.
- Every concurrently serving record — from the current prod record through
  the newest beta record (prod may lag beta by several records, not one) —
  must operate correctly against live data. Hold promotion when ring skew
  exceeds the supported window.
- Artifact and record retention lasts at least the supported rollback window
  (default 30 days). Destructive index/data cleanup waits until the oldest
  retained record has expired.

## Adoption

The target state above is adopted incrementally; sequencing, current scope,
and per-surface status live in the tracking issue
([#10049](https://github.com/BasedHardware/omi/issues/10049)), not in this
doc. Until a surface has joined the ring system, its currently documented
workflow (e.g. the traffic-only hotfix runbook) remains authoritative. The old
arbitrary-ref prod deploy workflows refuse prod artifact deploys; their
traffic-only repair path remains a deliberately narrow emergency tool.
