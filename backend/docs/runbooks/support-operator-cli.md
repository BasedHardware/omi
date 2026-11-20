# Support operator CLI (`omi-support-ops`, `scripts/support/ops.py`)

Not the read-only support harness (`omi-support`, [support-harness.md](support-harness.md)),
which a support person runs with their own Firebase session. This CLI runs on operator
cloud credentials and is the only path for holds, retention checks, DSAR exports and
account operations.

The one audited path for support work that touches customer data: legal holds,
retention checks, DSAR exports and allowlisted account operations. Support staff
do not run it with personal credentials; a support operator agent runs it on
their behalf, and every run is attributable.

## Rules

- Every command needs `--ticket` (the Intercom conversation id), `--actor` (the
  person who asked) and `--reason` (one line, no customer content). `--agent`
  (or `SUPPORT_AGENT_ID`) names the identity that ran it.
- Every command, read or write, first writes `support_actions/{action_id}` and
  then finishes it with `outcome` `succeeded` or `failed`. If the audit write fails, the
  command does not run. The audit document never contains customer content:
  only counts, states and digests.
- Writes are dry runs unless `--apply` is passed.
- Credentials: the operator's ADC. Today that is the `prod-operator` agent tier
  (`source ~/.local/bin/gcp-agent-env.sh prod-operator`); the dedicated support
  operator service account replaces it once provisioned. Never a human login.

```bash
cd backend
python scripts/support/ops.py --ticket 215476871538429 --actor "Aryan Gupta" \
  --reason "DSAR litigation hold" --agent support-vm hold status <uid>
```

## Legal holds

A legal hold blocks Omi's destructive paths for one account (the app delete route only; the developer API conversation delete does not check holds yet): account wipe,
conversation deletes (cascade or not), memory deletes, batch purges and
retention sweeps. It never blocks product access (P7 Decision 4). A held user
can still delete a conversation in the app: it disappears for them at once
(hidden + tombstoned, `X-Omi-Delete-Outcome: held_deferred`) and is physically
kept until the hold is released. A hold released while such a delete is in
flight falls through to the normal delete.

| Command | Effect |
| --- | --- |
| `hold status <uid>` | Hold document, deletion gate, account-deletion state, hold events, deletes made while held |
| `hold place <uid> [--review-by YYYY-MM-DD] --apply` | Places (or refreshes the audit fields of) a hold; default review in 180 days, at most 730; verifies the fence afterwards |
| `hold release <uid> --apply` | Releases; verifies deletion is permitted again; reports follow-up |
| `hold list [--all]` | Active holds, with `review_overdue` and `missing_audit` flags |

Placement contends on the same per-account gate as deletion: it is refused
while an account wipe or another destructive operation is running
(`DestructiveOperationInProgress`). Retry after it finishes.

Holds are account-wide. The hold document keeps `ticket`, `reason`,
`placed_by`, `placed_at`, `review_by` (and `released_by`, `released_at`,
`release_reason` on release); `legal_holds/{uid}/events/{id}` keeps every place
and release. Holds written before this CLI have no audit fields; `hold list`
flags them as `missing_audit`, and `hold place` on them backfills the fields.

### Hold release follow-up

- Cascade deletes made while held keep their erasure obligation. The runner
  finishes it `held`, re-checks hourly, and erases after release. Nothing to do.
- Non-cascade deletes made while held arm no erasure (the runner only performs
  cascades). `hold release` reports them under `held_deferred_deletes` with
  `erasure_armed: false` and prints a `follow_up` line. Their physical erasure
  is still owed after release. Until a `hold erase-deferred` command exists
  (tracked on SCA-3339), file the list on the ticket and the SCA issue. Do not
  erase by hand. If the tombstone scan reports `capped`, deferred deletes past
  the cap are not listed; escalate on SCA-3339 before closing the ticket.
- A held cascade delete does not cancel the conversation's action-item
  reminders until its erasure runs after release; the conversation itself is
  hidden at once.

### Kill switch

`LEGAL_HOLD_DEFER_SINGLE_DELETE=false` on the backend restores the previous
delete behavior for held accounts: a non-cascade delete physically erases, and a
cascade delete is answered `409 account_gate_busy`.

## What a hold does not cover

- Firestore backups and point-in-time recovery expire on their own schedule
  (7-day PITR, 28-day weekly backups at the time of writing). A hold does not
  extend them.
- GCS lifecycle rules (for example `playback/` deleted at 30 days in
  `omi-private-cloud-sync`) are bucket-wide. To keep specific objects, take a
  sealed copy (a GCS object `temporaryHold`) or a DSAR export.
- Logs, third-party processors (STT, LLM, vector stores) and data the user
  holds on their own devices.

## Retention check and DSAR export

`retention check <uid> (--conversation <id> | --month YYYY-MM)` lists what
survives for those conversations: Firestore records, audio objects (live,
noncurrent and soft-deleted), hold and gate state, and backup coverage. It is
read-only.

`dsar export <uid> --approval <intercom note id> --apply` builds the same content
as the in-app "Export All Data", plus retained audio, as a zip with a SHA-256
manifest in `gs://based-hardware-privacy-exports/<ticket>/`, and returns a V4
signed URL (7 days at most) signed through IAM, with no key file. Send the link
only to the account's verified email. The support owner approves each export on
the ticket; the agent checks the uid matches the ticket's contact first.

## Account operations

`account summary <uid>`: profile basics, plan, hold and deletion state. Write
operations are added one at a time after review. Deletes and refunds are never
offered here.
