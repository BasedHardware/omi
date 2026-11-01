# Scoped, silent held-batch redrive

This is an operator workflow, not an automatic retry. Paid apply needs explicit
approval of the exact cohort/plan digest and spend. Never reset recovery epochs,
remove prior receipts, or re-upload a terminal held unit to buy another call.

## Scope and bootstrap

`batch_pipeline_speech_redrive.py` requires an inclusive UTC quarantine window and
one owner pinned through an environment variable. Initial selection admits only
`quarantined / failed_held` jobs without a speech-redrive or silence-disposition
intent. Older failures and historical receipts are excluded. Owner reads use
200-row document-cursor pages, with a 20,000-document read budget; the selected
cohort remains capped at 200 units and 67 speech units. An optional private JSON
`--unit-ids-file` intersects the window and owner; every supplied ID must qualify.
It never authorizes a foreign, spent or out-of-window unit.

A dry-run checks privacy/ledger/artifact bindings, decrypts retained audio only in
memory, runs strict local VAD, and writes a **local, create-only mode-0600 cohort
file**. It makes no provider call or Firestore write. Its stdout contains only
counts, bounded failure reasons and digests. The cohort file contains private
identifiers/fingerprints: keep it outside Git, never attach or print it. Missing
or changed bindings fail closed. An existing file is replayed, never widened by
new qualifying jobs or replaced after the canary.

Securely inject `ENCRYPTION_SECRET`, `MODULATE_API_KEY`, and
`BUCKET_BATCH_PIPELINE` through the authorized operator workflow. Disable shell
tracing. No human GCP login is needed. Use a task worktree's own backend venv.
The following shell stages are separate approval boundaries; all variable values
are operator-scoped, not global configuration:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
backend/.venv/bin/python backend/scripts/batch_pipeline_speech_redrive.py \
  --stage prod --owner-env REPAIR_OWNER_UID \
  --quarantined-after "$REPAIR_START_UTC" --quarantined-before "$REPAIR_END_UTC" \
  --expect-count "$REPAIR_UNITS" --expect-speech-count "$REPAIR_SPEECH_UNITS" \
  --paid-epoch 2 --silent --cohort-file "$REPAIR_PRIVATE_DIR/cohort.json" \
  > "$REPAIR_PRIVATE_DIR/dry-run.json"
```

The first dry-run bootstraps `source_census_sha256`; it no longer needs a
precomputed source digest. Every apply **requires** that source digest, the
unchanged private cohort file and explicit `--approve-plan-sha256`. The plan
binds owner, namespace, unit fingerprints, VAD decisions, both time bounds,
optional ID scope, paid epoch, provider, and silent mode. Changing any requires a
new review. The full preflight completes before the first paid call.

## Silent serving prerequisite

**Deploy the corresponding serving/projection/enrichment code before any silent
paid apply.** Running only the new CLI against old serving code does not provide
silence. Verify the running release SHA and a non-production acceptance canary;
no deployment or production apply is part of merely opening this change's PR.

`--silent` is persisted in the immutable paid intent and cannot change on replay.
Assignment stamps `sync_silent_redrive_revision` in the same transaction as the
recovered transcript and carries silence in each projection receipt. Both sync
and async projection defer notification-capable donor task cleanup, retaining its
cleanup debt for later ordinary work. Enrichment reads the durable revision,
including an already pending outbox delivery, and regenerates notes with derived
effects deferred: no task/reminder delivery, memory/goal extraction, summary-app
fanout or creation webhook for that revision. Transcript, playback, usage and
content-ledger publication still converge. A later ordinary append advances the
revision and restores normal processing; silence is not a permanent account or
conversation setting. Independent user actions and later normal captures are
outside this repair's suppression scope.

## Paid canary, remainder and stopping

After the exact dry-run digest, spend and deployed silence contract are approved,
run the same args under `prod-operator`, adding these flags for one canary:

```text
--apply --source-census-sha256 <dry-run source_census_sha256>
--approve-plan-sha256 <approved plan_sha256> --apply-limit 1
```

Verify the result, ordered projection, ledger publication and absence of repair
notification/reminder scheduling. A `recovered` CLI result alone does not prove
publication. Get a separate go for the remainder, then repeat the exact cohort
and digests with `--apply-limit <total speech count>`. Limits are fixed sorted
prefixes: the larger limit includes the canary receipt, so a 58-unit cohort
permits at most 57 new calls after its canary. No cursor means “one more unit”.

Every non-success stops the CLI before the next unit and returns exit 2. A process
exception also stops work. Never continue after `failed_held`, `running_held`,
`allowance_held`, `disabled`, `policy_unpinned`, a fence or a changed digest.
There are no nested provider retries: paid epoch 2 calls Modulate once. A lost
result write leaves the intent running; replay reconciles the same create-only
artifact or stays held, never reissues the paid call. Stop launching further
units on a notification or cost anomaly. Keep all receipts/artifacts; rollback
cannot undo a vendor charge or published words. Never clear an intent to retry.

## Explicit independent recovery for ordinary empty units

`--ordinary-empty-independent --paid-epoch 3 --silent` is a separate operator
plan, with Soniox as its only new recognizer. It is not an automatic retry or
the language-guarded route. Initial selection requires exact private IDs,
`quarantined / failed_held`, an ordinary `assemble_words / empty_asr` worker
failure, valid input-bound worker speech of at least one VAD frame, and settled
Modulate-empty intents at both epoch 1 and epoch 2. The spent epoch-2 intent
must already be silent and match the original recovery and privacy generation.
Nonempty/unknown replies, a missing/foreign/subframe worker receipt, active
work, a result, or a prior Soniox attempt do not qualify.

Each owner-scoped plan is capped at two speech units and 47.6 recorded audio
seconds in total. The existing decoded per-unit independent bound is still
60 seconds. The census binds the exact worker receipt, worker failure and
spent intent, in addition to the usual immutable unit fields. The distinct
operation/plan digest also binds the fixed unit/audio ceilings and silent mode.
These limits do not authorize any call: the lead must approve each owner's
new census and plan digests and the combined call budget.

Use the same dry-run and canary approval boundaries as above, adding the new
mode, an exact `--unit-ids-file`, `--paid-epoch 3` and `--silent`. Dry-run reports
worker-VAD speech; it does not relabel that evidence as a fresh CPU-VAD test.
Keep its new cohort file separate from the spent Modulate plan. Before apply,
securely supply the approved Soniox runtime credential as well as the normal
artifact material. Privacy, policy, funding, lease and source-binding checks
remain mandatory. The independent-recovery kill switch still stops new calls.

Apply preserves both spent intents verbatim and creates one new Soniox intent
with an explicit ordinary-empty route marker. Valid words may project through
the already deployed silent serving contract. Empty, invalid or uncertain
answers remain held and retain their measured speech; this mode never turns an
empty reply into a silence result. Replay reuses the same intent and reconciles
only its create-only artifact, never buying another call. Changing the prior
proof or approval digest refuses the plan.

This operator code needs no batch-worker rollout. It still requires a reviewed
merge, a fresh canonical dry-run from that source, and separate lead approval
before production apply. Unit tests with synthetic providers do not establish
production recognition quality or visible transcript delivery.

## Local verification

Focused regressions cover scoped bootstrap/replay and silent projection. The
loopback-only `backend/scripts/batch_redrive_scope_emulator_test.py` exercises
real Firestore document cursors beyond 1,000 owner documents and read-budget
refusal. Run it with an isolated Firestore emulator, e.g.:

```bash
firebase emulators:exec --only firestore --project demo-p55-redrive \
  'backend/.venv/bin/python backend/scripts/batch_redrive_scope_emulator_test.py'
```
