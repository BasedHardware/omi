# Isolated JIT QA manual operator

`.github/workflows/jit_qa_manual_operator.yml` is the operator entrypoint for
the already deployed isolated QA plane. It does not deploy a service or job,
create a Scheduler trigger, build an image, call a model, or change a global
flag. Every dispatch must be from `main` and must name the immutable deployed
QA source SHA with a successful first-attempt Release Eligibility run. That
SHA must be an ancestor of current `main`; the workflow records both the
deployed source and the operator's current-main checkout so an unrelated main
commit does not force a QA image rebuild.

The fixed data-plane tuple is:

| Field | Value |
| --- | --- |
| GCP project | `based-hardware-dev` |
| Firestore database | `jit-qa` |
| Firebase Auth project | `based-hardware` |
| QA UID | `vi7SA9ckQCe4ccobWNxlbdcNdC23` |
| Cloud Run region | `us-central1` |
| drain job | `knowledge-ledger-drain-qa-job` |
| Required service API | `redis.googleapis.com` |

The workflow authenticates with the development GitHub environment's
`GCP_CREDENTIALS`. The auth action's generated `GOOGLE_APPLICATION_CREDENTIALS`
file is retained for Firestore ADC resolution; the workflow checks that it is
the action output and never prints its contents. Before a drain or rollback, it
reads the named job and rejects a different project, job name, runtime service
account, source label, image tag, customer credential selector, Firestore
database, or UID allowlist. The image must be a `gcr.io` development image
pinned by a SHA-256 digest and its `source-sha` label must equal the admitted
deployed source SHA. Before any credentialed operation, the runner
installs the pinned `backend/pylock.runtime.toml` environment and runs both
operator imports. Seed imports are deferred until after development
authentication and load the named `ENCRYPTION_SECRET` from Secret Manager in
process memory; the secret is never written to the receipt or workflow
artifact. Index operations use
`backend/scripts/jit_qa_firestore_index_operator.py` and do not import the seed
runtime.

Run the actions in this order for a fresh named database:

1. If deployment stopped at Redis API provisioning, run
   `ensure-infrastructure-api` with confirmation `ENABLE_QA_API`. It checks
   `redis.googleapis.com` in `based-hardware-dev` and enables it only when the
   service is not already enabled. This operation does not require a `run_id`
   and does not mutate a Redis instance or any Firestore data.
2. `indexes-plan` to inspect the two required named-database composites. If
   either is `MISSING`, run `indexes-apply` with confirmation
   `APPLY_JIT_QA_INDEXES`; this is restricted to the canonical
   `memory_items.updated_at + __name__` history query and the
   `conversations.discarded + status + created_at + __name__` entity-timeline
   query.
3. `bootstrap` with confirmation `PREPARE_QA`. This is create-only and fails
   before writing when any collection already exists.
4. `prepare` with the chosen lowercase synthetic `run_id` and confirmation
   `PREPARE_QA`. This creates only the 101 owned synthetic rows and evidence
   through `backend/scripts/jit_qa_seed_and_verify.py`.
5. `inspect` to capture the content-free pre-drain state.
6. `drain-verify` with `DRAIN_VERIFY_QA`. This executes the existing job three
   times using Cloud Run execution overrides, waits for each exact execution,
   parses its aggregate log line, and runs the seed operator's real durable
   100 + 1 + stable-retry verification. The persistent job gate is checked
   again after every execution and must remain `false`.
7. `rollback` with `ROLLBACK_QA` only after a reviewed successful proof. This
   calls the canonical writer-transition rollback helper and checks that all
   synthetic rows/evidence remain present with the same metadata digest.
8. `rollforward` with `ROLLFORWARD_QA` after rollback. This executes one
   bounded retry, requires zero migrated rows and one cutover, then verifies
   the canonical ledger fences are restored.

The `drain-verify` receipt joins the exact execution names to the aggregate
producer counters, the seed verifier result, and the Firestore completion and
prompt-projection fences. It contains no row content or provider payload. A
successful emulator proof is a code-contract result and cannot substitute for
the named Cloud Run execution and its real rollout/admission path.

The uploaded workflow artifact is limited to the content-free operator receipt;
raw Cloud Run descriptions, logs, Firestore documents, and temporary launch
files remain outside the artifact staging directory. Retain the receipt with
the separate isolated-plane readiness receipt. If any precondition fails,
preserve the failed receipt and fix the named QA resource or data-plane state
before retrying; do not point the operator at the shared development job.
