# Batch projection ambiguity and owner repair

The generation resolver still refuses an unproven target. Only its typed
`ProjectionGenerationAmbiguous` fence becomes an `ambiguous_generation` part
receipt (`quarantine_version=1`, state `quarantined`). That transaction rechecks
intake/result binding, content-ledger ownership, predecessor and privacy. It
writes no conversation. The final part atomically advances the owner watermark
and records `projection_state=quarantine_held` when any part is quarantined.
Proven parts retain their own receipts; replay never appends them twice.
The first held part upgrades that result's protocol to 2 with a
`lineage_quarantine_version=1` marker in the same transaction. Old binaries
require result protocol 1 and therefore cannot acknowledge an unknown held
receipt or turn a multipart hold into successful completion. New readers accept
protocol 2 only with a versioned held receipt. The intake/ledger protocol stays 1.

This releases successors while **withholding the ambiguous text**. It is not
successful delivery of that text. The upload remains incomplete, uncharged by
normal completion and ineligible for completion-only artifact/receipt TTLs.
Encrypted audio/results and intake proof remain for a separately reviewed
reconciliation. Never clear the receipt or move the watermark backwards to
replay held text: successors may already have been assigned. Privacy erasure
continues to override custody holds.

The repair CLI processes only committed results for one owner. It does not
commit result-ready jobs, rerun providers, reset paid intents, flip flags, or
release failed-held recovery jobs. Ordinary serving reconciliation commits
eligible result-ready jobs after projection debt falls.

## Lead procedure

Deploy the reviewed backend image first. Verify the serving release SHA on
every traffic-bearing projector revision. Run in the matching secure backend
runtime with existing bucket/encryption/task configuration; supply the owner
through `DAVID_UID` without printing it. This lane does not run these commands
in production.

1. Source `~/.local/bin/gcp-agent-env.sh ro-prod`. Run
   `python scripts/batch_pipeline_projection_repair.py --stage prod` from backend.
Dry-run performs bounded metadata reads only, without policy pinning or
artifact loading. Save its aggregate JSON and `plan_sha256`.
Local emulator rehearsal uses `--stage local [--local-namespace <id>]`: the
tool then builds an anonymous-credentials client against the loopback emulator
and a `batch_pipeline_test_<id>` namespace; `--local-namespace` is refused on
`--stage prod`, which stays fixed on `batch_pipeline_prod`.
2. After explicit operator authorization, source the `prod-operator` tier and
   rerun with `--apply --approve-plan-sha256 <digest>`. A changed plan refuses
   before writes. Assignment, follow-up, accounting and publication reuse
   ordinary replay-fenced projector code. No transcription provider is called;
   ordinary conversation enrichment may be enqueued and incur its usual LLM cost.
   Any `unpinned_units` refuses apply: the lead must establish policy through
   the serving role first; the repair cannot persist laptop/operator settings.
   Operator repair also requires an authenticated manifest and active lineage
   and live-dedupe fencing for every new non-native speech assignment. Missing
   source proof, an excluded cohort or a disabled fence blocks the unit instead
   of taking whole-batch or temporal assignment. A new speech part must bind a
   proven generation or enter ambiguity quarantine; unbound and stamp-fallback
   outcomes require separate serving-role reconciliation. Already persisted receipts
   can finish without reassigning text. No switch is changed by the tool.
3. Repeat a dry-run after crashes, concurrent progress or `forward_truncated`.
   The default is at most 1,000 forward rows plus 100 backward rows for lost
   follow-up replies. `--max-units` (up to 5,000) and `--lookback-units` (up to
   1,000) are explicit bounds, not proof that an entire owner history was scanned.
   `lookback_truncated` means older follow-up debt may need separate inspection;
   `lookback_missing` means the backward walk stopped at a retention-expired
   (absent) historical receipt — forward discovery still runs from the watermark
   id, and an existing foreign or relabeled historical row still refuses.
4. Verify durable successor completions and client publication, falling pending
   counts/ages and held receipts. Quarantine is an open obligation, never a
   success count. Record unresolved held speech separately; this tool does not
   adjudicate the old generation overlap.

## Fifteen-minute deadline

`omi_batch_projection_obligation_oldest_age_seconds` uses the indexed discovery
query with a one-row limit across pending, persisted, ready and quarantine-held
states. Age starts at commit, including quarantines indefinitely. The 900-second
deadline alarms; it never deletes data. A failed sample leaves the timestamp
`omi_batch_projection_obligation_observed_at_seconds` unchanged.

The lead installs `charts/monitoring/batch-projection/alerts.yaml` with the
serving metric scrape. The overdue rule requires a sample younger than 120s;
the stale rule catches an exporter that still scrapes but cannot refresh,
including a never-observed zero (`observed_at` stays 0 when every sample has
failed since startup) — the rule's 2-minute pending duration is the only
startup grace.
Scrape absence requires the fleet's target/no-data monitoring. Rule installation
and notification delivery need separate live verification. No alert is applied
by this repair or PR. Rollback: deploy the prior image; already held receipts
remain fenced and must not be deleted; an older image cannot finish a partially
assigned protocol-2 result, so resume it with this repair-capable image.
