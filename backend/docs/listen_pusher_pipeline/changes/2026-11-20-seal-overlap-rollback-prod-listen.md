# Seal overlap rollback on prod listen

## What changed

Since [PR #25660](https://github.com/BasedHardware/omi/pull/25660), the backend-listen chart refuses a
literal `privateEnv` overlay on any stage that sets `privateSecretEnv.keys`, which prod does. The
seal overlap rollback in the pipeline doc still named `privateEnv.RECORD_SEAL_OVERLAP_TRIM_ENABLED=false`
for listen, and that path no longer renders in prod.

The contract section now says how each stage rolls back:
- **Prod:** `RECORD_SEAL_OVERLAP_TRIM_ENABLED` stays a literal in `prod_omi_backend_listen_values.yaml`.
  It is not one of the Secret Manager keys, so rolling it back is a reviewed PR plus a listen deploy.
- **Dev:** the `privateEnv` override still works.

`test_cpu_admission_switch_is_declared_in_runtime_manifest_and_listen_chart` now checks both sides on
prod: the plain render carries `true`, and the chart refuses the overlay.

## Rollout and flags

This is docs and test only. There is no flag or runtime change.
