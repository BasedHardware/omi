# GitHub WIF for notifications-job development

Creates a dedicated pool/provider/SA for `gcp_notifications_job.yml` on
`based-hardware-dev` only. Not the #9842 OpenTofu plan pilot. Not GKE
workload identity. Not Owner.

State backend is operator-supplied (`~/.hermes/opentofu/gha-wif-notifications/development.backend.hcl`).
Do not declare the state bucket in this module.

Prod input of the same workflow keeps `GCP_CREDENTIALS` until a later slice.
