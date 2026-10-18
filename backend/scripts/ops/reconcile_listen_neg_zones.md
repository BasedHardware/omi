# Listen standalone NEG reconciliation

GKE creates a zonal standalone NEG for each listen pod zone through the
`cloud.google.com/neg` Service annotation, but it does not add newly created
NEGs to the global load-balancer backend service. A Ready listen pod can
therefore receive no WebSocket traffic when it lands in a zone that is absent
from that backend service.

After the production listen rollout and readiness checks, run
`reconcile_listen_neg_zones.py` against the Service's
`cloud.google.com/neg-status` annotation. It lists exact-name NEGs across
zones, compares them with the backend service, and copies the existing
balancing mode, per-endpoint request limit, capacity scaler, and (for
`IN_FLIGHT`) traffic duration when attaching missing zones. The script fails
if status declares a zone whose NEG is not listable or if attached backends do
not agree on the settings to copy. `--dry-run` performs the same reads and
reports zone names and counts without attaching anything.

The production deploy identity needs exactly these Compute permissions:
`compute.backendServices.get`, `compute.backendServices.list`,
`compute.backendServices.update`, `compute.networkEndpointGroups.get`, and
`compute.networkEndpointGroups.list`. A permission denial must fail the
deploy; grant the permissions through the deployment IAM process rather than
adding them here.
