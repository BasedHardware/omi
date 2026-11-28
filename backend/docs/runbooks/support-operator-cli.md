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

- Every command needs `--ticket` (the Intercom conversation ID or issue reference), `--actor` (the
  person who asked) and `--reason` (one line, no customer content). `--agent`
  (or `SUPPORT_AGENT_ID`) names the identity that ran it.
- Hold, retention, export and summary commands first write `support_actions/{action_id}` and
  then finish the record with `outcome` `succeeded` or `failed`. If the audit write fails, the
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

### Correct a stale canceled Stripe plan

`account correct-plan` operates on one owner (`--owner`) or a committed file
with one owner per line (`--owners-file`). It requires a ticket, actor, reason
and the UTC packet date (`--since YYYY-MM-DD`). Use the private triage checkout
with directory mode 0700, and store all input lists and receipts under
`packets/`. Keep owner arguments out of shell history and transcripts.
Set `OMI_SUPPORT_TRIAGE_ORIGIN` to the approved private Forgejo SSH URL.
The command checks this against the checkout’s effective fetch and push URLs.
The command prints counts and Firestore document reads. The private JSONL
receipt contains the per-owner plan diff and the audit mapping.

Supply the restricted live `STRIPE_PLAN_CORRECTION_READ_KEY` from the operator credential loader.
The command sends Stripe GET requests. It changes the Omi subscription plan
and clears a verified stale price in the same transaction as the audit.
It preserves the subscription association for late payments. It checks the
owner’s current Stripe customer and canceled subscription, other subscription authority, invoices,
charges, pending checkout, legal holds and deletion markers. Missing or
conflicting evidence stops the affected owner. Stripe evidence is refreshed
immediately before the Firestore transaction. The transaction fences the
profile and hold/deletion documents within Firestore. Stripe and Firestore
have separate transaction boundaries. Discovery covers the Omi billing
customer and historical Stripe customer or subscription metadata tied to
the owner. Stripe does not index Checkout Sessions by owner. Before apply,
resolve any known checkout or customer without one of those bindings
through the private support workflow.

1. With the `ro-prod` tier, run `account correct-plan` without `--apply`.
   Use a new packet-relative path for `--receipt`. Review the results privately,
   then commit and push the dry run to `main` on the private Forgejo origin.
2. Use a reviewed, merged CLI and the `prod-operator` tier. Fetch the private
   origin, select the canary, then run with `--apply` and
   `--dry-run-receipt` pointing to the committed dry-run receipt (up to
   24 hours old). Use a distinct `--receipt` for every invocation.
3. Before the canary, confirm the serving entitlement readers cannot reload
   the stale paid price. An already-Basic record with a stored price needs
   private eligibility review. Verify the canary projects Basic with a matching
   audit, a corrected count of one, and zero failures.
   Apply batches of up to ten ready owners. Stop on any failed batch or any
   newly pending checkout or unclear guard. Commit each receipt to the private
   origin. The Firestore plan and per-owner content-free audit are written
   together. A prepared receipt entry with no verified result means the
   outcome needs reconciliation before retrying.
4. To roll back one owner, supply `--rollback-receipt` pointing to the
   committed apply receipt and use the same ticket and list date. Dry run
   first. With `--apply`, the command restores the previous plan and price
   state only while both audit digests and the Firestore version still match
   the original correction and the current guards pass.

Set `OMI_SUPPORT_CORRECT_PLAN_ENABLED` to `false`, `off`, `0` or `no` to
disable plan writes from this command.

## Transcription credit

Gives one account extra managed transcription, spent only after the plan's
monthly allowance runs out, for live and batch alike, until it expires
(default 30 days, at most 90). Use it when a customer's recordings are parked
behind the cap and support has decided to process them (ruling: David
2026-11-27, SCA-5263). There is no size limit; the audit record is the control.

```bash
cd backend
source ~/.local/bin/gcp-agent-env.sh prod-operator
export OMI_ENV_STAGE=prod  # the parked-audio scan reads batch_pipeline_prod and refuses without it
python scripts/support/ops.py --ticket T --actor A --reason R transcription-credit status UID
python scripts/support/ops.py --ticket T --actor A --reason R transcription-credit grant UID --hours 32
python scripts/support/ops.py --ticket T --actor A --reason R transcription-credit grant UID --hours 32 --apply
python scripts/support/ops.py --ticket T --actor A --reason R transcription-credit revoke UID GRANT_ID --apply
```

- `status` and the dry run print the plan allowance, usage this month, the
  usable credit, and the account's parked batch units and seconds.
- The grant records the month's usage at grant time, so usage before the grant
  never spends it, and a month reset never hands it out again. `grant` refuses
  when this month's usage is unreadable (no baseline), or when the parked scan
  was truncated, unless `--allow-partial`.
- A malformed stored credit counts as no credit. `status` lists its keys;
  `revoke UID KEY` removes the bad key without parsing the rest.
- Held batch work is released all at once per account, at the account's next
  hold check (about 5 minutes; the command never touches held jobs). Usage is
  metered after admission, so `--apply` refuses a grant smaller than the parked
  audio unless `--allow-partial` accepts the overrun.
- Releasing parked work also runs Omi's summary and memory processing for those
  conversations (that gate passes the cap by default); the grant covers STT only.
- Usage displays stay plan-only: the app still shows the plan's minutes as used
  while recording works on the credit.
- Each command writes one `support_actions` record; the grant is stored under
  that record's action id in `users/{uid}.support_transcription_credit`.
- A retried `--apply` after a timeout makes a second grant. Run `status` first.

### Kill switch

`SUPPORT_TRANSCRIPTION_CREDIT_ENABLED=false` on the admission services
(backend, backend-sync, backend-integration and the batch workers) makes
admission ignore every stored credit without erasing it. Work already admitted
still completes.

### Apple and Google sign-ins on separate accounts

When Apple and Google sign-ins point to two established Omi account IDs,
each account keeps its own subscription, recordings, conversations, and
integration grants. Mobile linking keeps the original session active when
the new sign-in method already belongs to another account. Guest migration
uses a separate flow with proof tied to the anonymous source account.

1. Help the customer sign in to the original account on a client that offers
   its original sign-in method. For an Apple account, use **Sign in with
   Apple** and the same Apple Account. If a device has unsynced recordings on
   its current account, keep that session active and use another supported
   client, or let the current account's recordings sync before signing out.
2. Ask the customer to verify their plan and open a conversation they recognize
   on the original account. Existing integrations stay with the account that
   authorized them. To connect an integration on the original account, have
   the customer verify the active account before granting it access.
3. If Support needs to verify both accounts, use the existing private ticket.
   Have the requester demonstrate a fresh sign-in to each account separately
   using its provider. In the mobile app, **Settings → Account → User ID**
   copies that session's account ID. Use the audited `account summary <uid>`
   for each independently verified ID to confirm the recorded plan and account
   state. Treat copied IDs, emails, relay addresses, and screenshots as lookup
   evidence only. The requester enters credentials with the provider and
   shares only the account IDs through the private support channel. If control
   of either account remains unclear, leave both accounts in place and escalate
   the verification privately.
4. Keep both accounts intact during recovery. Before any support-assisted
   account change, record explicit consent in the private ticket for the
   affected accounts, the specific action, and its expected effects. Then use
   an approved operator procedure for that action.
