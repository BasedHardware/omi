# Batch queue safety: late work and incomplete scans

The queue guard targets 30-minute commitment age. Grafana's
`omi-batch-queue-uncommitted-2h` rule sends a human Telegram alert when a fresh
queue sample contains a compute commitment older than two hours for five
minutes. It covers all admission epochs. Import the committed Grafana rules
through the monitoring runbook; a merged JSON file is not a live alert.

`oldest()` and `oldest_retry()` skip deliberate policy holds and rows in
`dead`, `quarantined`, `committed`, or `privacy_blocked`. These rows retain their custody
and recovery obligations. A completed terminal-disposition marker does **not**
exempt `result_ready`: its ordered commit is still owed. Unknown states remain
measured. The broader timeliness alarm separately covers quarantine, assignment
holds and projection; this queue proxy does not prove delivery to the user.
That delivery rule is promoted into the existing Grafana import gate with a human
page tier; its diagnostic companions remain agent tier. The lead must dispatch
the production import and verify live definitions after deploying this fix.

A bounded scan reads at most 501 documents. If the first 500 are all exempt and
a sentinel remains, it exports NaN, meaning unknown age. It must neither invent
late work from a hold's enqueue time nor publish a healthy zero. Prometheus
`max` can ignore NaNs beside finite priorities, so the guard separately counts
`age != age` and reports BLIND. The page-tier
`omi-batch-queue-safety-blind` rule alerts after five minutes of scan blindness
or absent observations, or after queue freshness is stale for fifteen minutes
plus five minutes pending. Capacity and timeliness sampling continue independently.

## Triage without weakening custody

Use `ro-prod` and metadata aggregates. Count states and bounded reason codes;
never read user content, print owners, or delete source audio. Read the guard's
`batch_safety` log and compare age, `age_incomplete`, and freshness. An allowance
hold is an admission decision, not poisoned audio. Let its normal authorized
re-evaluation proceed; never waive allowance or redrive it to silence a metric.

For actual failures, use the existing fenced paths:

- Worker failure: `Scheduler.fail` / `quarantine_job` retains encrypted audio,
  removes the queue commitment and opens held recovery. Never patch state by
  hand or reset a paid intent.
- Failed-held speech: `scripts/batch_pipeline_speech_redrive.py` requires an
  owner/time/unit cohort, fresh census digest, paid-epoch authorization and
  bounded apply. Provider/abandoned-running outcomes are not proof of silence.
- Proven silent failed-held: `scripts/batch_pipeline_held_disposition.py` uses
  strict VAD and the silence contract. Positive or unknown speech is refused.
- Exhausted validated empty: `scripts/batch_pipeline_terminal_empty.py` requires
  the exhaustion evidence, lineage/privacy checks and approved plan digest;
  language-guarded units require independent recognizer evidence.
- Committed projection debt: `scripts/batch_pipeline_projection_repair.py`
  replans and applies one owner's fenced projection. A `result_ready` queue
  row must first pass normal ordered merge; projection repair is not a shortcut.
- Privacy-blocked: retain the privacy fence. No audio recovery is authorized
  across it.
- Historical dead records: the authenticated `/redrive-dead` handler uses
  `Scheduler.redrive_dead` and its privacy transaction. It does not waive custody
  or authorize a new paid recovery epoch.

Production disposition is an operator decision, separate from this signal fix.
The lead owns worker/guard deployment and Grafana import. Verify the worker's
serving image identity, then a new bounded age/BLIND reading, and read back the
live alert UID, page tier, receiver and absence of the agent mute interval.
Do not test notification delivery by notifying users.

Rollback: restore the prior worker image and guard chart and restore the Grafana
rule backup through the documented importer. Preserve the audited worker HPA
min 6 / max 12 and baseline 6; do not restore the stale 4/16 chart values.
Disposition/redrive cannot be undone by
resetting a paid token; stop further apply, preserve durable receipts, and
replan after an uncertain result.
