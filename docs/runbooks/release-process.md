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
  "helm_values": { "backend-listen": "gs://…/values/<id>/backend-listen.yaml#sha256:…" },
  "run_config": { "backend": "gs://…/run/<id>/backend.yaml#sha256:…" },
  "secret_versions": { "OPENAI_API_KEY": "projects/…/versions/42" },
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

Per-ring configuration lives in source-controlled values
(`backend/deploy/runtime_env.yaml` lanes + Helm values), so every beta/prod
difference is reviewable in the PR that introduces it.

## Deploying and rolling back

`deploy <ring> <release_id>`:

1. Resolve the record from the bucket; refuse anything else.
2. Snapshot the ring's active serving state (a receipt) before any mutation.
3. Cloud Run: create no-traffic revisions from recorded digests → smoke check
   the revision URL → shift traffic.
4. GKE: apply charts with recorded digests and values, wait for rollout,
   verify with `backend/scripts/deploy_status_report.py`.
5. On deterministic failure before or immediately after the traffic switch:
   restore the pre-mutation snapshot automatically (Cloud Run: shift traffic
   back; GKE: one `helm rollback` attempt). If restoration also fails, write
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
workflow (e.g. `gcp_backend.yml`, the hotfix runbook) remains authoritative.
