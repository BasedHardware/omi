# Development WIF read-only plan pilot

This module creates exactly one development-only GitHub Workload Identity Federation path for issue #9842:

- pool: `omi-opentofu-9842-dev`;
- provider: GitHub OIDC, restricted to immutable repository ID `776121034`,
  owner ID `162546372`, the dedicated workflow, `development` environment, and
  `main`;
- service account: `omi-tofu-plan-dev-9842@based-hardware-dev.iam.gserviceaccount.com`; and
- grant: project-level `roles/browser` only. It does not grant access to
  project resources, but it does allow the probe's `resourcemanager.projects.get`
  call and project IAM-policy metadata reads.

It deliberately grants no Secret Manager role, no Storage write role, no Service
Account Token Creator role, and no ability to deploy Cloud Run/GKE resources.
The GitHub workflow performs a read-only `google_project` data-source plan with
no remote backend, refresh, lock, or apply path.

The separate validation workflow uses a single checked-in,
`offline-validation-only` token literal solely to initialize the Google provider
for the bootstrap's backend-free, no-refresh plan. It is invalid for GCP and
the guard rejects any different token or credential source. It saves the plan
and asserts that it has exactly the five approved creates before CI passes.

## Operator bootstrap

This PR does not apply the module. A separately approved development operator must first create a dedicated, versioned GCS state bucket with uniform bucket-level access and retain its name outside source control. Then the operator initializes this module with the reviewed bucket config, runs a saved plan, and applies that saved plan using a write-capable development-only identity.

After the bootstrap read-back confirms the provider, service account, and one
`roles/browser` grant, dispatch `OpenTofu Development WIF Pilot` from `main`.
Its expected proof is successful GitHub OIDC exchange plus a `google_project`
read of `based-hardware-dev`. Record the workflow URL and metadata-only
read-back on [issue #9842](https://github.com/BasedHardware/omi/issues/9842).

Do not import existing resources, add a production backend config, or run this module against `based-hardware`.
