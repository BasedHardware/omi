# Listen canary ownership and image admission

`backend/scripts/render_listen_canary.py` renders **only** the chart's Deployment,
renames it `prod-omi-backend-listen-canary`, pins a registry digest and fixes
replicas. Prod requires an explicit coordinator-captured main Deployment
snapshot: its pod template preserves live Helm/env overrides as well as
resources, probes, node scheduling, service account,
secrets/config refs, scrape annotations and graceful termination. The caller
reviews the YAML before applying it. No cluster calls occur while rendering.

| Option | Assessment |
| --- | --- |
| Optional second Deployment in main chart/release | Small template, but routine upgrades supplying the checked-in disabled values remove it. `helm.sh/resource-policy: keep` leaves ambiguous ownership/stale config and is not an enablement authority. Requires durable overrides in every release writer. |
| Separate coordinator-applied chart render (chosen) | No new Helm release object or workflow input; main upgrade/rollback cannot prune the separate Deployment because it has never been in that release manifest. Digest, replicas and env remain pinned. Removal is one ordinary Deployment deletion. |
| Separate Helm release | Can work, but stock chart releases change Service instance labels and create extra Service/SA/Ingress/HPA. A chart refactor solely for this is larger. |

The canary uses both existing Service selector labels and adds `track=canary`
to its own selector/pods. Main's historical selector is broader; its immutable
selector cannot be narrowed on an existing Deployment. Distinct Deployment and
ReplicaSet ownership fences keep reconciliation separate. **Do not orphan the
canary ReplicaSets** or strip their owner references: the broader main selector
could then adopt an orphan. Test contracts cover the rendered controllers and
Service selectors, not a claim of observed production distribution.

Main HPA targets only main; it does not scale canary. Production pod discovery
copies Kubernetes `track` into the target label `listen_track` on every
`backend-listen-metrics` series, including `up`. The adapter's listen series
and averaging queries select that job/namespace and exclude
`listen_track="canary"`. Main pods with no track label remain eligible. Canary
metrics stay in the same scrape job, so fleet health watches still include
canary harm. The existing PDB's broad selector includes canary pods; check main
readiness and capacity at each step.

The coordinator must deploy **both** monitoring values changes before creating
canary pods: the production kube-prometheus-stack scrape config and the
production prometheus-adapter rule. The listen deployment workflow deploys
neither. Follow the linked rollout card's monitoring prerequisite, verify live
config and external metric, and remove canary before rolling either back.

Use an escaped exact pod-name regex for canary PromQL; the scrape still copies
pod name and namespace. `listen_track="canary"` is an additional isolation
verification selector, not a substitute for pinned pod identities/exposure.
Both canary endpoints join the existing Service/NEG. Balancing
is by ready endpoints for **new connections**, with LB locality/capacity effects;
long sockets do not move. Observe actual accept counts instead of inferring
session share from replicas. GKE NEG health attachment must be checked live.

Routine Helm runs never manage this Deployment, but shared ConfigMap/Secret/SA
changes still affect it (env on pod replacement; mounted secrets independently).
Record their revisions and refuse unrelated STT configuration changes during
the bake. Regenerate from the same reviewed chart source for expansion; do not
silently render a newer main chart. Review routine deploy changes, refresh pod
identity/exposure after restarts, and preserve simultaneous controls.

Keep the initial control snapshot for every expansion render. A new snapshot
would silently change canary configuration. Compare the initial snapshot with
main immediately before apply; if a routine deploy changed STT settings,
HOLD/review rather than continuing with unlike controls. Snapshot capture is
read-only deployment metadata, never customer documents or secret payloads.

## Image facts verified from the current workflows

- `gcp_backend.yml` has `release_sha`, no arbitrary build branch. Both prod and
  development require a full SHA that is an ancestor of fresh main, plus a
  successful main push Release Eligibility proof. Break-glass relaxes the proof
  only, **never** the ancestry guard; do not use it for this rollout.
- `gcp_backend_auto_dev.yml` is driven by successful main Release Eligibility
  workflow runs, re-admits the newest eligible main commit and builds that SHA.
  It cannot build #20391's unmerged head.
- `gcp_backend_listen_helm.yml` checks out main for prod (requested branch for
  dev), never builds an image, and requires a prod image tag to be an ancestor
  of main. Its dev branch input is a chart source, not a dev image factory.
- The deploy composite builds/smokes/pushes
  `gcr.io/<compute-project>/backend:<git-short=7-sha>`. `cloud-run-only` still
  builds and promotes Cloud Run; `all` also rolls listen. There is no build-only
  dispatch here. Tags are naming conventions, not registry immutability; the
  manual canary uses the resolved `@sha256` digest.

Recommend **merge to main inert**, dev-build/soak, then canary active. The prod
GKE nodes' ability to pull the dev registry image must be verified by the
coordinator; do not add IAM. If they cannot, use an existing prod digest built
from that SHA or obtain scoped approval for the existing prod Cloud Run release
that also builds it. Do not hand-build/push a production image outside Actions.

## Request to #20391's author (not implemented on this branch)

The report's earlier `9271b67fcc` head has since advanced and the branch is
still moving. Resolve its final head/CI at qualification time; preserve report
§8 gates and review the actual final diff. The inspected branch has no complete
default-off switch. Existing `STT_ROUTING_MODE=shadow`, on0 and
`STT_RESILIENT_RECONNECT=false` do not disable cross-provider recovery changes.

Have its author add `STT_FAILOVER_RECOVERY_ENABLED`, default **false**, keeping
the prior receiver/replay/adapter/rejection behavior for false/unset. True must
cover the new owner controller, shared dial budgets, bounded replay/writer path,
capture birth/deadline handling and 429 breaker behavior; gating just the
receiver leaves shared adapter/chain changes active. Preserve flag-off rollback
through the attended rollout. Set code, dev/prod chart and runtime defaults
false and add flag-off baseline equivalence plus flag-on existing matrix tests.
This is a multi-module implementation/review, not a one-line env addition;
the author owns it because only they should revise the recovery PR. An estimate
in lines would be misleading until the strategy seams are chosen. The canary
renderer supports explicit env overrides; the soak manifest sets the proposed
flag true. **They do not establish that the image recognizes it.** Coordinator
must verify that implementation before merge-first deployment. Full enablement
is a subsequent config PR aligned across chart and runtime overlay.
