# Live evidence before production raises

`backend/scripts/rollout/live_preflight.py` is the shared primitive used by
`omi_flags.py set`, `omi_flags.py delete`, `omi_flags.py import-posthog --apply`, `ramp_set.py --apply`
and production controller ADVANCE writes. It uses the credentials already held
by the operator command (prod-operator for production writes); it never selects
a tier, installs credentials or calls the fleet bus. Dry-run ramp commands do
not perform production preflight reads.

All writers use `widens_exposure` before invoking liveness evidence. Percent
increases, activation, allow UID additions and deny UID removals widen exposure.
Percent decreases, deactivation, allow UID removals and deny UID additions
narrow it. Deletion returns the key to PostHog and requires preflight for a
possible 100% exposure, unless the current rule is active at 100% with no deny
UIDs. Use deactivation or a decrease for emergency rollback. `_ramp` and the
controller merge percent changes without deleting overrides; clearing an
operator lock leaves serving percentages intact.
A mixed write refuses with `RAMP_PREFLIGHT REFUSE mixed_write`
and exit 2, including dry-run requests; run the narrowing change alone first,
then the raise. `--accept-not-live` cannot override a mixed write.

The prover first fetches `origin main` with a bounded timeout; a failed fetch
emits `RAMP_PREFLIGHT UNREAD origin reason=fetch_failed` (exit 4).
The runtime containment roster comes from named-ref backend reading sites and
`backend/runtime_images.json`. Shared utils/config/database/models code checks
the backend, pusher and batch image families; routers/services check backend
and pusher; diarizer code checks the batch family. Record-seal is derived from the batch chart
as a consumer of the same image; the registry also drives direct deploy admission
and does not declare child deployments separately. The uninstalled sync-backfill pilot is excluded.
`_ramp` names bind the runtime reader and the name's writer schema so older
readers cannot silently reject a newly written name.

The gate refuses at the first missing proof:

- `key_unread`: no runtime reading site.
- `not_live`: a runtime's serving commit lacks any required code/registry commit (including
  introductions on parallel branches), or no
  single 100% Cloud Run revision / no GKE pod can be established.
- `commit_unbound`: a serving image cannot be bound to a local Git commit.
- `scrape_unknown runtime=<name>`: the runtime has no job in the expected-targets
  inventory. Cloud Run jobs instead prove their current template image/release
  SHA and emit `NOTE scrape_not_applicable runtime=<name>`; the clean metric
  check still applies. Other unknown platforms fail closed.
- `scrape_dead`: the declared job has no samples or any `up` sample differs
  from 1 during the last 30 minutes.
- `metric_dead`: the first `\bomi_[a-z0-9_]+\b` name in `ramp.clean_metric` has
  no nonzero series in the last 30 minutes. Prose without a metric token emits
  `RAMP_PREFLIGHT NOTE metric_unparsed key=<K>` and skips only this check.

Transport, malformed responses, missing Git history and deadline errors emit
`RAMP_PREFLIGHT UNREAD <what> reason=<fixed-token>`. Refusals exit 3, unread
exits 4, PASS/OVERRIDE exit 0. Controller failures HOLD the affected advances.
Pure narrowing bypasses both this preflight and its Git fetch, including when
production evidence is unavailable. Existing writer authority, CAS, quality
floor and fleet-gate rules still apply.

A deliberate exception uses `--accept-not-live 'a reason at least 15 characters'`.
It appends `accept_not_live:<reason>` to the existing flag-store audit reason or
`_ramp` history reason. `_ramp` keeps the original short reason token in its
serving document, preserving compatibility with deployed readers; the full
explanation is in the same transaction's history row. No notification service
is required for a write.

Cloud Run binds the actual traffic revision, preferring
`OMI_BACKEND_RELEASE_SHA`, then its image tag / image labels, then `commit-sha`.
GKE checks all nonterminated matching pods, including old replicas during a
roll. Digest bindings read the authenticated registry manifest and Docker
config labels using the operator's access token. `omi.release.tree` can bind
older digest images to the oldest content-identical commit on the named main
lineage. Missing bindings refuse instead of inferring from deployment times.

Tests use a temporary Git repository and canned service, revision, pod, registry
and Prometheus payloads. They do not obtain credentials or make production calls.
Trains are not gated here: deployment is how new code becomes live. The
meta-repo env writer gate and drift report are separate deliverables.
