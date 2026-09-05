# Isolated JIT QA manual operator

`.github/workflows/jit_qa_manual_operator.yml` is the operator entrypoint for
the already deployed isolated QA plane. It does not deploy a service or job,
create a Scheduler trigger, build an image, call a model, or change a global
flag. Every dispatch must be from `main` and must name the exact current
`main` commit with a successful first-attempt Release Eligibility run.

The fixed data-plane tuple is:

| Field | Value |
| --- | --- |
| GCP project | `based-hardware-dev` |
| Firestore database | `jit-qa` |
| Firebase Auth project | `based-hardware` |
| QA UID | `vi7SA9ckQCe4ccobWNxlbdcNdC23` |
| Cloud Run region | `us-central1` |
| drain job | `knowledge-ledger-drain-qa-job` |

The workflow authenticates with the development GitHub environment's
`GCP_CREDENTIALS`. It never prints or exports that credential. Before a drain
or rollback, it reads the named job and rejects a different project, job name,
runtime service account, source label, image tag, customer credential selector,
Firestore database, or UID allowlist. The image must be a `gcr.io` development
image pinned by a SHA-256 digest and its `source-sha` label must equal the
admitted commit.

Run the actions in this order for a fresh named database:

1. `bootstrap` with confirmation `PREPARE_QA`. This is create-only and fails
   before writing when any collection already exists.
2. `prepare` with the chosen lowercase synthetic `run_id` and confirmation
   `PREPARE_QA`. This creates only the 101 owned synthetic rows and evidence
   through `backend/scripts/jit_qa_seed_and_verify.py`.
3. `inspect` to capture the content-free pre-drain state.
4. `drain-verify` with `DRAIN_VERIFY_QA`. This executes the existing job three
   times using Cloud Run execution overrides, waits for each exact execution,
   parses its aggregate log line, and runs the seed operator's real durable
   100 + 1 + stable-retry verification. The persistent job gate is checked
   again after every execution and must remain `false`.
5. `rollback` with `ROLLBACK_QA` only after a reviewed successful proof. This
   calls the canonical writer-transition rollback helper and checks that all
   synthetic rows/evidence remain present with the same metadata digest.

The `drain-verify` receipt joins the exact execution names to the aggregate
producer counters, the seed verifier result, and the Firestore completion and
prompt-projection fences. It contains no row content or provider payload. A
successful emulator proof is a code-contract result and cannot substitute for
the named Cloud Run execution and its real rollout/admission path.

The workflow artifacts are content-free and should be retained with the
separate isolated-plane readiness receipt. If any precondition fails, preserve
the failed artifact and fix the named QA resource or data-plane state before
retrying; do not point the operator at the shared development job.
