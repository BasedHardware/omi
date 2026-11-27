# Soniox alert-only Grafana provisioning

David approved the one-rule route for `omi-batch-soniox-daily-hours`. Use the existing **Provision Grafana dashboards** workflow on `main` with `environment=prod`, `alert_scope=soniox-alert`, and `alert_operation=apply`. This scope skips every dashboard step and the full alert-set apply. It shares the protected `prod` Environment and `grafana-alert-provisioning-prod` lock used by the existing alert path. Workflow and helper-only commits are excluded from the push trigger, so merging this change does not itself apply dashboards or alerts.

Do not approve or re-dispatch Grafana run `46045070289`: Release cancelled it on 2026-11-27. That broad run could update Ops and Business dashboards plus the repository alert set and had no exact inverse for all planned writes. Keep uncapped routing off until the scoped apply is approved and readback confirms the page is serving.

## Apply one rule

Dispatch the existing workflow on `main` with the inputs above. Before any write, the alert script reads live rules and receiver state, validates the committed KeepLast canaries and probes their datasources. It saves the target's live preimage, or an absent marker, together with the desired definition and source SHA/run ID. It writes only the Soniox UID and reads it back against the committed definition. The preimage is uploaded as `grafana-soniox-alert-backup-<run_id>` for 15 days.

The active page is `omi-batch-soniox-daily-hours`, with the 1,500 h/24h threshold. Release posts a `SERVING:` readback (or equivalent) on SCA-4917 after the live page rule is verified. Only after that readback may the uncapped route serve; post the route-table readback against the 1,500 h/24h page on SCA-4917.

## Roll back that apply

Dispatch **Provision Grafana dashboards** on `main` with `environment=prod`, `alert_scope=soniox-alert`, `alert_operation=restore`, `source_run_id=<apply run ID>`, and `source_sha=<full apply SHA>`. This uses the same prod approval and concurrency lock and downloads only that apply's artifact.

The restore tool is dry-run by default. The workflow supplies its explicit apply confirmation only after artifact validation. If the rule was absent before apply, rollback `DELETE`s the Soniox UID and verifies absence. If it existed, rollback `PUT`s the captured definition and verifies it. It refuses to overwrite a concurrent live edit. No other alert UID, dashboard, folder, contact point, or notification policy is written.
