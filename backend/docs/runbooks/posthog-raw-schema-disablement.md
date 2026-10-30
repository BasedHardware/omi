# PostHog raw-schema disablement

Parent-owned. This runbook does not change PostHog, BigQuery, IAM, grants, or
scheduled jobs. Do not add a PostHog billing aggregate or a scheduled query.
`pull_gcp.py` and `web/admin/lib/services/gcp-billing.ts` already read the
current billing export directly. `web/admin/lib/services/plan-economics.ts`
reads `omi_finops.unit_cost_daily`, `plan_revenue_daily`, and
`unit_cost_reconciliation`. None of those need a warehouse copy of PostHog.

## Schemas to disable

Disable every raw schema, including ones that still look active. Set
`should_sync: false` and turn scheduling off (`sync_frequency: never`). Then
confirm no job for that schema is running or retrying. Do not retry a failed
schema to "see if it works."

| Schema | Last known state | Action |
|---|---|---|
| 26,069,209-row billing schema | Failed | `should_sync: false`. Do not resume it. |
| 10,022,630-row billing schema | Last sync around 2026-10-06 | `should_sync: false`, scheduling off. |
| 2,818,940-row billing schema | Last sync around 2026-10-06 | `should_sync: false`, scheduling off. |
| 7,312,520-row schema | Synced 2026-10-12; may still be inside the 7-day free window | `should_sync: false`, scheduling off. A later full refresh is billable. |
| `gcp_billing_export_resource_v1_01B896_918303_539138` | Predecessor billing account, no rows after 2026-07-01 | `should_sync: false` if PostHog has it. Never sum it into finops. |
| `cloud_pricing_export` | Public price list, if present | `should_sync: false`. It is not Omi usage. |
| `gcp_billing_export_resource_v1_01B287_9348DC_02D256` | Current account resource export | Turn off the **PostHog** sync only. Leave the BigQuery export itself running. Direct readers depend on it. |
| Klaviyo, Shopify, Stripe, Meta Ads (three sources) | Inside the residual row rate; exact counts were not separated | Inventory each schema (id, row estimate, sync type, schedule, webhook support, last success, running/retrying jobs) before `should_sync: false`. |

The four large billing schemas above sum to about 46,223,299 rows. Which PostHog schema id maps to which physical table was not stored in this repo. Match them in the PostHog source list before flipping flags, and record the id you disabled.

## Order of operations

1. Inventory every warehouse schema, including SaaS sources and any schema that is failed, paused, or inside its free week. Write down running and retrying job ids.
2. Set `should_sync: false` and scheduling off on every raw schema. The free-week cap check does not apply to sources younger than 7 days, so the flag is the control, not the spending limit.
3. Re-check jobs. A running or retrying sync can still finish and bill. Wait until those jobs are stopped or have failed closed. Do not start them again.
4. Confirm direct BigQuery still answers: `pull_gcp.py` against the current resource export, and the admin plan-economics read of `omi_finops`.
5. Only then set the PostHog data-warehouse spending limit to **$200**. Notify at **$160** (80%) and **$200** (100%). Leave the limit at $1,200 only if a 26M-row refresh is an accepted cost. It is not.
6. The $200 check is skipped for a source under 7 days old, is read from a short cache, and does not stop a sync that already started. That is why step 2 comes first.

## Rollback

Roll back by reading BigQuery directly (`pull_gcp.py`, `gcp-billing.ts`, `plan-economics.ts`). Do not turn a raw PostHog schema back on. There is no automatic re-enable. Restoring `should_sync: true` is a new decision, not a rollback.

## What stays

`omi_finops` tables are partitioned by `date` with no partition expiry. Grains:

| Table | Grain | Cluster |
|---|---|---|
| `unit_cost_daily` | date, segment_type, segment, component, method | segment_type, segment, component |
| `unit_cost_reconciliation` | date, pool | pool |
| `plan_revenue_daily` | date, plan, snapshot_date | plan |
| `unit_cost_user_day` | date, uid_hash, cohort, plan | cohort, plan |

Recompute today and the prior two UTC dates idempotently (`net = gross + credits`, credits signed). Older dates change only through an explicit date-range reconciliation. The predecessor export is never included. Logic and fixtures: `backend/scripts/finops/gcp_cost_reconciliation.py`.
