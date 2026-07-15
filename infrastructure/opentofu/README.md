# OpenTofu foundation

This directory is the future source of truth for durable GCP foundation resources only:

- GitHub Workload Identity Federation pools, providers, and CI service accounts;
- dedicated runtime service accounts and additive IAM grants;
- Secret Manager containers and Secret Accessor bindings, never secret payloads or versions; and
- GCS state-bucket metadata and narrowly scoped state access.

Cloud Run and GKE releases remain owned by GitHub release workflows. OpenTofu must never write images, service or job templates, revisions, tags, traffic, runtime environment variables, secret references, GKE workloads, or secret values.

## Initial no-mutation slice

`foundation/main.tf` deliberately declares no resources. The backend shape and Google provider constraint are checked in now so the module can be validated without a GCP identity, a remote state bucket, a project ID, or an API call.

The CI workflow uses only `contents: read`. It validates the source with the backend disabled, then copies the module to a temporary directory with the backend block removed before generating an offline empty plan:

```sh
tofu -chdir=infrastructure/opentofu/foundation init -backend=false -input=false
tofu -chdir=infrastructure/opentofu/foundation validate
python3 .github/scripts/check_opentofu_foundation.py --prepare-offline-plan-module /tmp/opentofu-foundation-plan
tofu -chdir=/tmp/opentofu-foundation-plan plan -refresh=false -lock=false
```

It then checks the generated plan is empty. `check_opentofu_foundation.py` allows only the foundation resource families above and rejects all data sources, Cloud Run, GKE, release artifacts, arbitrary resources, and Secret Manager version/payload paths.

## State bootstrap and live pilot

The `.backend.hcl.example` files are placeholders, not executable configuration. Follow the staged manual work recorded in [issue #9842](https://github.com/BasedHardware/omi/issues/9842) before initializing a real backend or authenticating a plan. Keep development and production state isolated, and never add secret payloads, secret-version resources, or secret-value data sources to this module.
