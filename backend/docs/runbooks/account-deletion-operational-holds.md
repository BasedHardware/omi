# Account deletion blocked by operational storage holds

User-requested account erasure overrides Omi's operational audio preservation.
A genuine legal hold still blocks erasure. Never clear all GCS holds based on
their age, bucket, or an untagged `temporaryHold=true` value.

The account worker releases only exact generations in a reviewed operator
approval on the server-owned `account_deletions` marker. The initial recovery
format supports the legacy `expiry-20261017` campaign in `syncing-local`, at
most 1,000 generations per approval. Other campaigns or larger plans require a
separate reviewed change. A failed job remains fenced and retryable.

## Prepare and review

Run the tool from a task checkout containing this fix, using `ro-prod`. It
refuses unless exactly one failed deletion exists, reads deletion metadata and
only that owner's GCS metadata, and joins only that prefix's preservation
control rows. It does not read audio, memories, or transcripts. All held
generations must match the campaign's audited restored-generation proofs.
Before and after that owner-scoped query, the tool checks both opaque SQLite
artifacts against the preservation operator's completed-campaign SHA256
receipt and rejects nonempty WAL overlays. A directory name or a matching
generation from an unrelated ledger is insufficient proof.

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
backend/.venv/bin/python -I backend/scripts/account_deletion_operational_holds.py \
  --single-failed-job \
  --preservation-audit-dir /private/preservation-receipts \
  --plan-output /private/release-plan.json
```

The private plan contains hashes, generation/metageneration pairs and a digest;
stdout contains only a count and digest. Review the plan, campaign provenance,
account intent, current legal-hold authority, and the exact backend-sync release
identity. The new worker must serve the task endpoint before registration.
The tool does not deploy or prove a deployed revision. Record the reviewed
digest and approval reference before the write step.

## Approved operator execution

Only the separately authorized operator runs this step. Resolve the live
backend-sync URL with a metadata-only service read, then append
`/v1/users/account-deletion-wipes/run`. Do not use a signed-in customer API.
The tool independently reads only `uri` from the exact production backend-sync
Cloud Run resource and rejects a supplied URL that differs. Omitting
`--handler-url` uses that verified URI directly.

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator
backend/.venv/bin/python -I backend/scripts/account_deletion_operational_holds.py \
  --single-failed-job \
  --preservation-audit-dir /private/preservation-receipts \
  --approved-plan /private/release-plan.json \
  --apply-digest REVIEWED_SHA256 \
  --approval-ref REVIEW_REFERENCE \
  --enqueue --handler-url VERIFIED_BACKEND_SYNC_DELETION_HANDLER
```

Registration re-reads the full generation plan, checks the reviewed digest,
acquires the account gate, validates legal-hold authority inside its transaction
and binds approval to the existing failed job. It does not release holds or
delete data itself. It wakes the same opaque job through the existing OIDC
Cloud Tasks path. If queue creation fails after registration, the approval
remains durable and ordinary reconciliation retries the failed job (backoff
capped at one hour). Do not reset the intent, delete the gate, or create a new
account/deletion job to force progress.

The worker requires its running marker and matching account gate, rechecks
legal holds, refuses event-based holds, retention and unknown object metadata,
and pins both generation and metageneration for PATCH and DELETE. The worker
checks custom legal/hold/retention markers before unheld or unapproved objects
can return to the purge as well. Each release
has a durable intent and outcome under
`account_deletions/{uid}/operational_hold_releases`; receipts contain no UID or
object name. An ambiguous PATCH success is reconciled only against that intent
and its single expected metageneration increment. Metadata changes fail closed.

Verify metadata-only: the original marker reaches `completed`, its gate reaches
`completed`, the approved owner prefix has no remaining live/noncurrent
generations, and release receipts have terminal outcomes (reconcile any pending
intent against object absence). Check the completion log/metric on the running
release. A code merge or successful hold release does not prove account erasure.

Stop and escalate any active/malformed legal hold, changed generation or
metageneration, unknown metadata, unproven campaign source, changed job, or
existing different approval. Do not overwrite an old approval automatically.
