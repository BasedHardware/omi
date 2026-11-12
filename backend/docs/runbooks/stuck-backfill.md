# Historical stuck-conversation backfill

This is an operator-only, explicitly approved migration. Shipping this code does
not scan accounts, redrive jobs, close rows, or arm a run. Forward stale-recovery
and disconnect fixes must ship first. Then ship this policy to **every consumer
of the finalization queue**, verify the running release identity and a silent
synthetic canary, and obtain separate approval for the operator-account canary and each fleet
cohort. No production execution is authorized by this runbook or a plan digest.

## Durable silent policy

`ProcessingTrigger.SILENT_BACKFILL` reuses server recovery's run-now, reprocess,
KEEP, strict transcript, source/privacy, protected-output, job and live-session
guards. The immutable finalization job stores both `processing_trigger` and
`delivery_policy=silent_backfill_v1`, plus its operator run ID. A mismatched
policy/trigger refuses worker execution. Retries and completed-row replays use
that durable policy rather than a request-scoped silent switch.

This first version deliberately enriches **title and summary only**. Extracted
structured action text may appear inside the notes; it is never materialized as
a reminder/task. No memory, task, goal, app or lazy-effects queue is started.
The completed row records `terminal_no_derived_effects=true`. The winning
finalization claim closes without external integrations, push/proactive/client
created delivery, smart merge, duplicate linking, keyframes, voice learning or
episode/Dream/persona triggers. List reads see the normal completed row.
A processing-budget denial fails silent substantive work before a deferred
title-only row can be persisted or accepted as a successful backfill.
No global notification/Dream switches are changed. A later explicit user action
may reprocess the row normally; the historical job itself always stays silent.

Keep queue consumers on a policy-aware release while any silent job is queued,
leased or retryable. Pre-policy workers do not refuse these jobs: their unknown-trigger fallback
selects CLIENT_FINALIZE and executes the historical job loudly, including full
automatic fanout. They must never consume a silent job. Before an old
source rollback, stop admissions and drain or suspend the historical work;
rolling code back alone is not a safe rollback of in-flight jobs.

## Counts-only preview and private plan

Run inside the approved production operator runtime using the task worktree's
Python 3.11 environment. Supply encryption material through the runtime, never
shell output. Source `~/.local/bin/gcp-agent-env.sh prod-operator`. No human
GCP identity is used. `--dry-run` performs reads only and emits aggregate counts;
`--plan PATH` also writes a new local mode-0600 private plan. Neither creates
cloud tasks or mutates production documents. The owner allowlist is a local
0600 newline-separated file; the operator-account canary uses exactly one owner. IDs and
revisions remain in private plans/journals, never stdout or public artifacts.

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/stuck_backfill.py \
  --dry-run --owner-allowlist /private/owners \
  --cutoff 2026-10-22T02:17:14.930173Z
# Replace --dry-run with --plan /private/plan.json for an approval artifact.
```

Default substantive triage is T2: >=60 speech-union seconds OR >=100 Unicode word
tokens. The plan defaults to a $100 modeled
fleet cap; `--max-modeled-usd` changes it in the approval artifact. The durable
run cap may be lower, never higher than its approved plan cap. Known valuable
candidates receive a separate state check: completed/job-bound rows are excluded
from noise and receive no duplicate admission.
Thresholds are plan-bound. No age-only discard: age only orders work.
Decode failures are review. Empty transcript plus audio references is review,
never assumed silence. Other below-T2 rows use reversible noise close. Active
BYOK owners are refused for managed historical summaries; no absent user key is
replaced with platform credentials. Locked/discarded/deleted/deferred/local-pending/protected
rows are skipped. Plans bind row update timestamps at nanosecond precision and
recording-session revisions. Account privacy and leases are checked again in
the admission/close transaction. Each owner inventory and the full cohort are
bounded; exceeding a bound refuses planning rather than silently truncating it.

Review the plan outside public logs. A SHA256 binds bytes, **not human approval**.
After explicit GO, an operator may create `stuck_backfill_runs/{plan.run_id}`
with these fields (this is a production write and is not performed by preview):

```json
{
  "enabled": true,
  "approved_plan_sha256": "<reviewed bytes sha256>",
  "verified_delivery_policy": "silent_backfill_v1",
  "verified_release_sha": "<running artifact identity, all queue consumers verified>",
  "silent_canary_evidence_ref": "<current-release synthetic canary: zero automatic deliveries>",
  "queue_consumers_evidence_ref": "<all queue/replay/pusher consumers on policy-aware release>",
  "admissions_per_minute": 10,
  "max_admissions": 10,
  "max_modeled_usd": 1
}
```

These release fields are operator attestations, not an automatic live identity
probe. They must be backed by release/runtime evidence before arming the run.
The control and reservation refuse missing canary/consumer evidence references.
These references are still operator attestations, not machine verification of
their contents. Before expansion, review the current-release silent canary and
all-consumer receipts. Before a pre-policy rollback, stop admissions and prove
that no silent job remains queued, leased or retryable; a source rollback alone
is unsafe. No script guesses readiness from local source or a merged PR.

## Apply and stop controls — separate GO required

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/stuck_backfill.py \
  --apply-approved-plan /private/plan.json --approved-plan-sha256 <digest> \
  --owner-allowlist /private/owners --receipts-dir /private/run-receipts \
  --batch-size 10 --spend-receipts /private/vendor-spend.json
```

The script checks owner scope, immutable plan bytes and newest-first order. It
paces all admissions, including noise close, with a transactional global slot
in the run control. Rate is at most 1000/min and is a cap, never promised
throughput. An atomic per-owner finalization pointer prevents another historical
job while the previous one is incomplete, across processes or restarts. The
script also awaits each exact job/generation terminal success before moving on;
this version is intentionally sequential. A changed generation, refusal, failed
job, timeout or first canary error stops and disables the shared run. Already
admitted jobs retain their normal durable ownership/retry behavior.

Set the run document's `enabled=false` to stop new admissions. The script checks
it between admissions, pacing waits and terminal polls. A transaction reserves
rate/budget before admission; a crash may consume a slot without doing work,
which is conservative. Before each paid admission the script also checks reconciled actual spend
plus this batch’s modeled reserve against the approved cap; actual totals over
the cap disable the shared run. A batch can exceed its estimate before vendor
usage is reconciled, so this is an admission/stop cap rather than a vendor-side
billing limit. Never replace scheduling limits by adding workers.

Private per-batch journals start incomplete and record each outcome plus exact
job/revision identities. A crash or lost ACK leaves the batch incomplete and
requires manual review; it is **never blindly replayed**. A complete journal
can be skipped on resume only after spend reconciliation and an exact match of
batch size and ordered item-identity digest; changing batch boundaries refuses
rather than silently skipping rows. Receipts expose
aggregate outcomes, modeled upper USD and actual spend. Missing actual spend is
`null`, never zero, and blocks the next batch. The operator supplies vendor
usage/billing evidence (including retries) in a mode-0600 ledger:

```json
[{"plan_sha256":"<digest>","batch":1,"actual_usd":0.01,
  "vendor_evidence_ref":"<private authoritative usage/billing receipt>"}]
```

This evidence is an operator assertion, not automatically validated vendor
billing. The operator must reconcile all serving vendors/gateway usage; no
account-day cost delta is falsely attributed to the backfill. Each substantive
row reserves $0.0033 (P54's $0.0011 summary model ×3); noise reserves zero LLM
USD. Summary/model rates and actual spend need re-checking before expansion.

## Reversible noise close

`database.stuck_backfill.close_noise` performs one transaction. It checks the
exact plan revision, stale/guard state, the recording-session revision and active
lease, owner in-flight state, privacy and the next deterministic job. It changes
only `status=completed`, `discarded=true`, `terminal_no_derived_effects=true` and
its versioned metadata marker. The marker snapshots the prior presence/value of
those three fields. Transcript, audio references and other content are untouched;
there is no deletion, decoder, provider or delivery call in the close seam.

Restore is bound to the close transaction's **commit timestamp**, never a later
read that could hide an intervening write. It also refuses changed session/job/
privacy/lease state and the wrong run, restores prior field presence and values,
and removes only the close marker. Restoring noise does not finalize it.

After an explicitly authorized restore, use the private completed batch receipt:

```bash
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/stuck_backfill.py \
  --restore-noise /private/run-receipts/batch-00001.private.json \
  --approved-plan-sha256 <digest> --run-id <run-id> \
  --owner-allowlist /private/owners
```

Substantive finalization has no atomic rollback of summaries or incurred vendor
spend. Stop future admissions; preserve durable job/generation identities. Do
not delete derived data or rewrite historical transcripts as a rollback.
