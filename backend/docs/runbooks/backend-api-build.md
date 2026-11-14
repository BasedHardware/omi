# Backend API artifact preparation

This contract prepares a backend API role image and an existing-workflow
consumer. It grants no build execution, installation, production change,
startup, traffic, feature-enable or broader surface authority. Release owners
must obtain the separate exact-source admission for each operation.

In the existing `gcp_backend.yml`, `mode=build-only, build_scope=backend-only`
builds, smoke-verifies and publishes only `backend-api:<sha12>`, with full
admitted revision identity and an immutable registry digest. It skips the
shared `backend:<sha7>` image, the local baseline, other Python roles and
native listen-edge. `role-images-prod` records the resulting release vector.
The default `build_scope=all` retains all existing build outputs. A non-default
build scope is rejected outside manual build-only, cloud-run-only, gateway-off.

The role image copies shared backend source and dependencies. This is a
service/image artifact boundary, not isolation from listen code or a promise
of zero observer-related I/O. No runtime env or serving traffic is changed by
build-only. Builds still consume runner resources, retrieve dependencies,
execute Docker instructions/probes and write registry/log/artifact outputs.

The companion workspace wrapper exposes `build-only SHA --build-scope
backend-only`. It retains **Cloud Run plus listen** admission, the clean
window, index readiness, lock, peak restriction, eligibility, requester and
prod Environment/WIF gates. Artifact scope is not hold scope. A successful
dry-run is a preview, not real dispatch admission. No target override or peak
override is part of this contract. The natural 22:00Z boundary lifts peak
alone. Approval after queue waits rechecks union hold/peak gates; the generic
path-only `approve-own` command is not a supported recovery route for these
builds. An interrupted build wrapper requires release-owner disposition,
not reclassification as a Cloud Run deploy.

After a separately admitted successful build, use its verified backend-api
digest and full source SHA for the existing manual consumer contract:

```
omi-deploy-prod cloud-run FULL_SHA --services backend --backend-api-image gcr.io/PROJECT/backend-api@sha256:DIGEST
```

This is contract syntax, not authorization to execute it. The wrapper rejects
other services, tags, malformed digests and foreign projects before external
access, verifies main exposes the required inputs and forwards
`service_images=backend=<digest>`. The workflow independently checks project
repository, role and full revision label before mutation. Only this exact
backend consumer skips the redundant shared-image build/smoke/push; legacy
and other service combinations retain their existing behavior. The selected
backend deployment retains runtime manifest/live-env validation, drift
reporting, release identity, traffic-by-revision and the printed concrete
revision rollback. It does not deploy sync, integration, backfill, listen or
gateway and does not alter their admission contracts.

Before execution the release owner must qualify the exact runtime/control
revisions and successful build vector, apply the existing privacy/operator
prerequisites and canary/drain-stop packet, and install only qualified tooling.
The SCA-1840 accepted source and its required pre-warm feature values remain
governed by that release disposition; newer code or successful artifact builds
do not supersede it. Existing break-glass and R15 own-run approval facilities
do not grant source/workflow edits or feature-enable authority.

To withdraw this preparation, leave the PRs unmerged and retain installed
versions and holds. After source adoption, omitting the new build scope and
image option restores the legacy contract. This is not a serving rollback;
use the release packet's independently captured revision rollback for that.
