# Typed Cloud Run service selection

SCA-2225 Train 2 retro items 1–4; rollout-lead source authorization
`01a1e149-3a35-71b8-b63c-9cee427e9921` (2026-11-15 22:16Z).

Use the existing protected `gcp_backend.yml` deploy path. Optional
`cloud_run_service=all|backend|backend-sync|backend-sync-backfill|backend-integration`
defaults to `all`, preserving the existing four-service behavior. A named target
requires the production manual `mode=deploy, deploy_targets=cloud-run-only`
boundary. It does not apply to build-only, traffic repair, auto-dev or GKE.
A mismatched integration-only canary/selector refuses before side effects.

A selected service retains the existing immutable source/image, Firestore,
service identity, runtime binding, readiness, candidate, traffic snapshot,
promotion, source verification and failure/cancellation inverse contracts.
The full source manifest still validates statically. Live runtime/vector
verification and every Cloud Run writer operate only on the selected set.
Omitted services receive no deploy, sidecar, traffic, IAM/env-fold or verification
mutation. Shared shell loops and per-role steps are independently covered by
executed fake-transport tests. A frozen step census refuses an unclassified step.
No flag, scaling, secret, service account or resource policy is changed here.

Keep `prod-train`, the existing shared workflow group, native holds and Release
agent caps. This is not independent-group fencing or parallel activation.
Manual/repair/ramp/rollback/break-glass writer participation must be reconciled
before any later parallel activation. No deployment or capacity change is
performed by source publication.

The existing Release wrapper owns a durable per-service operation from intent
through dispatch identity, run/attempt, environment approval, remote terminal
state and actual serving readback. An uncertain POST must never be retried or
bound by a creation-time window. A process exit retains `awaiting_reconciliation`;
resume proves the recorded run and actual traffic before release. The product
run name binds the actual selected service and full admitted application SHA,
separately from the requester/operation identifier.

After successful native serving-vector verification the existing composite
publishes only `cloud-run-selection-RUN-ATTEMPT`: a bounded JSON receipt with
schema, admitted application source, immutable workflow control SHA, selection,
run ID and attempt. No environment, secret reference or private snapshot is
included. The consumer independently fetches GitHub run/artifact metadata,
checks the archive digest and exact receipt bindings, and re-reads selected
serving and omitted-service identity/config/traffic before releasing custody.
A successful build or workflow terminal state alone is not a serving proof.
Missing API capability or incomplete/mismatched metadata remains refused.

The native traffic snapshot contains only the selected services. Failure or
cancellation restores that captured named inverse, not `latest` or a rebuilt
old image. Integration canary recovery retains its private within-run journal;
this selector adds no private journal export or new rollback executor. Release
alone owns operational use under current source, runtime and guard admission.

Tooling rollback disables the adapter while retaining the global lock and the
fail-closed durable reservation fence. Unresolved operations must not be erased
or bypassed by restoring a legacy writer. Source tests/green CI/independent SHIP
remain separate from installation, live qualification and actual serving.

Selected roles stamp `OMI_BACKEND_RELEASE_SHA` from the admitted application SHA. After the sidecar creates the final named receiving revision, provenance verification reads that exact revision and service ownership before promotion. Omitted services are neither stamped nor verified as part of the selected operation. The native run identity also proves `prod-train`, normal eligibility and default image selection before approval.

Named sync deploys resolve the backfill queue and handler/audience through the existing lifecycle helper in read-only `routing` mode, from the immutable workflow-control ops source. The omitted backfill worker and shared queue reconciler do not run. Missing ops queues or project-number metadata refuse before the sync deploy; application-manifest queue values cannot override this control binding.
