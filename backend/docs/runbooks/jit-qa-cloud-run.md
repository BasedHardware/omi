# Isolated JIT QA Cloud Run plane

`.github/workflows/jit_qa_cloud_run.yml` is the only entrypoint for the
isolated cloud proof. It is manual, accepts a dispatch from `main` only, and
requires the exact current `main` SHA to have a successful first-attempt
`Release Eligibility` run. The workflow uses `based-hardware-dev` in
`us-central1` and creates four explicitly named resources:

- `backend-jit-qa` — the API service;
- `desktop-backend-jit-qa` — the desktop companion API;
- `knowledge-ledger-drain-qa-job` — the ledger migration job; and
- `daily-memory-sweep-qa-job` — the bounded daily sweep job.

The resources use bare development ADC and the dedicated
`jit-qa-runtime@based-hardware-dev.iam.gserviceaccount.com` runtime identity.
They use the `(default)` Firestore database in `based-hardware-dev`, while
Firebase token verification is explicitly addressed to `based-hardware`.
`SERVICE_ACCOUNT_JSON`, `GOOGLE_APPLICATION_CREDENTIALS`, and
`FIREBASE_AUTH_CREDENTIALS_PATH` are rejected. The workflow never copies the
shared runtime environment, Redis/cache settings, Typesense or Pinecone
bindings, queue endpoints, connector credentials, notification providers, or
customer data credentials. The only Secret Manager bindings are the
development project's `ENCRYPTION_SECRET:latest` and `OPENAI_API_KEY:latest`.
The two API services accept Cloud Run's public transport so the application can
validate the normal Firebase bearer token; application authentication remains
the boundary for user routes.

The drain and sweep jobs are deployed with their gates closed. The drain
allowlist contains only the existing named-app QA UID
`vi7SA9ckQCe4ccobWNxlbdcNdC23`; no account data is copied or seeded by this
workflow. `run_once=true` additionally requires the literal confirmation
`RUN_ONCE`, checks `run.jobs.runWithOverrides`, and executes each job once with
bounded overrides. The sweep override uses `gpt-5.6-luna`, eight candidates,
and a `$0.80` model budget. The workflow captures the exact returned execution
names, polls `status.conditions[type=Completed].status`, and uploads a
content-free receipt. It does not create a Scheduler trigger or mutate IAM,
Firebase Auth, feature flags, or Firestore indexes.

Before the first dispatch, an operator must provision the named runtime service
account and grant only the required development resources: Cloud Run deploy and
read/run permissions to the GitHub development identity, `iam.serviceAccounts.actAs`
on `jit-qa-runtime`, Artifact Registry push access for the four QA repositories,
and the runtime service account's Firestore access in `based-hardware-dev`.
The isolated companion/model gateway tuple and Vertex permission are a separate
reviewed prerequisite; this workflow intentionally does not point at the
shared development gateway or any shared cache/queue.

The local functional fallback is
`scripts/dev-harness/jit_qa_local_stack.py`. It is useful for emulator contract
proofs but is not evidence that the cloud companion, gateway, or real Firebase
identity path is serving.
