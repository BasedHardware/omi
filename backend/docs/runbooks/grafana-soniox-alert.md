# Soniox alert-only Grafana provisioning

David approved the one-rule route for `omi-batch-soniox-daily-hours`. Use the existing **Provision Grafana dashboards** workflow on `main` with `environment=prod`, `alert_scope=soniox-alert`, and `alert_operation=apply`. This scope skips every dashboard step and the full alert-set apply. It shares the protected `prod` Environment and `grafana-alert-provisioning-prod` lock used by the existing alert path. Workflow and helper-only commits are excluded from the push trigger, so merging this change does not itself apply dashboards or alerts.

Do not approve or re-dispatch Grafana run `46045070289`: Release cancelled it on 2026-11-27. That broad run could update Ops and Business dashboards plus the repository alert set and had no exact inverse for all planned writes. Keep uncapped routing off until the scoped apply is approved and readback confirms the page is serving.

## Apply one rule

Dispatch the existing workflow on `main` with the inputs above. The first step reads live rules and receiver state, validates the committed KeepLast canaries, probes their datasources, and saves the target's preimage (or an absent marker) plus its Grafana resource version. The workflow uploads that artifact before the apply step starts. The apply re-reads the target, aborts if its resource version changed, and sends Grafana's versioned AlertRule API precondition so a concurrent update between the re-read and write returns a conflict when unified alert-rule storage is enabled. The versioned endpoint can also serve legacy storage, which ignores `resourceVersion`; Release must confirm production uses unified alert-rule storage before dispatching apply or restore. Endpoint availability alone does not establish this. The script fails closed if the versioned API is unavailable. It preserves the live rule group's provenance; repository alert writers share the same production concurrency lock. The preimage is uploaded as `grafana-soniox-alert-backup-<run_id>` for 15 days.

The active page is `omi-batch-soniox-daily-hours`, with the 1,500 h/24h threshold. Release posts a `SERVING:` readback (or equivalent) on SCA-4917 after the live page rule is verified. Only after that readback may the uncapped route serve; post the route-table readback against the 1,500 h/24h page on SCA-4917.

## Roll back that apply

Dispatch **Provision Grafana dashboards** on `main` with `environment=prod`, `alert_scope=soniox-alert`, `alert_operation=restore`, `source_run_id=<apply run ID>`, and `source_sha=<full apply SHA>`. This uses the same prod approval and concurrency lock and downloads only that apply's artifact.

The restore tool is dry-run by default. The workflow supplies its explicit apply confirmation only after artifact validation. If the rule was absent before apply, rollback `DELETE`s the Soniox UID with a resource-version precondition and verifies absence. If it existed, rollback `PUT`s the captured resource with the current resource version and verifies it. A concurrent edit between the read and either write returns a conflict. No other alert UID, dashboard, folder, contact point, or notification policy is written.
