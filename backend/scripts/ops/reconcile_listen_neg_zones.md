# Listen standalone NEG reconciliation

GKE creates a zonal standalone NEG for each listen pod zone through the
`cloud.google.com/neg` Service annotation, but it does not add newly created
NEGs to the global load-balancer backend service. A Ready listen pod can
therefore receive no WebSocket traffic when it lands in a zone that is absent
from that backend service.

After the production listen rollout and readiness checks, run
`reconcile_listen_neg_zones.py` against the Service's
`cloud.google.com/neg-status` annotation. It lists exact-name NEGs, keeps only
the zones the Service's status declares — `gcloud compute
network-endpoint-groups list` covers global, regional, and all zonal scopes by
default, while GKE only guarantees custom NEG name uniqueness within a region,
so a same-named NEG elsewhere is rejected instead of attached — compares them
with the backend service, and copies the existing
balancing mode, per-endpoint request limit, capacity scaler, and (for
`IN_FLIGHT`) traffic duration when attaching missing zones. The script fails
if status declares a zone whose NEG is not listable or if attached backends do
not agree on the settings to copy. `--dry-run` performs the same reads and
reports zone names and counts without attaching anything.

The production deploy identity needs this Compute permission set:

- `compute.backendServices.get` and `compute.backendServices.update` on the
  target global backend service, plus `compute.backendServices.list` at project
  scope.
- `compute.networkEndpointGroups.get` and
  `compute.networkEndpointGroups.list` at project scope, plus
  `compute.networkEndpointGroups.use` on each target zonal NEG.
- `compute.globalOperations.get` at project scope: synchronous
  `add-backend` polls the global operation it creates.

A permission denial must fail the deploy; grant the permissions through the
deployment IAM process rather than adding them here.
