# Local Sync Cloud Tasks stack gauntlet

Run this loopback-only gauntlet when changing Sync v2 admission, Cloud Tasks
dispatch, worker ownership/retry, staged-audio handling, or the Sync content
ledger:

```bash
npm run test:sync-cloud-tasks-stack:emulator
```

It needs the backend virtual environment, root Node dependencies, Redis, and
Java 21+ for the Firestore emulator. The runner gives Firebase a fresh
loopback port, starts a private loopback Redis, and starts **separate**
admission and worker ASGI processes. Their environment is allowlisted and has
an empty home/cloud configuration; it carries no cloud credentials, provider
keys, proxies, or developer Redis/Firestore endpoint. Both processes reject
non-loopback DNS and socket traffic. Each scenario uses a unique synthetic
user namespace, so concurrent gauntlet invocations cannot share local Sync
workspace material.

The exercised path is:

```text
multipart PCM v2 upload → real Sync admission → filesystem staging leaf
  → real tasks_v2.Task → strict loopback task recorder
  → separate real OIDC-protected /v2/sync-jobs/run worker
  → real Redis lock/job state + Firestore content ledger
  → deterministic VAD/STT/conversation leaves → durable status/readback
```

Before upload, the isolated admission process seeds a minimal server capture
using the production conversation encoder, then requests a real signed
`/v2/sync-capture-manifest`. The upload therefore takes the fresh,
device-bound admission branch; it does not use a test-only route override.

The recorder accepts only the production `tasks_v2.Task` shape: the configured
queue and named identity, loopback worker URL, POST/JSON transport, OIDC
audience/service account, opaque durable body, and 1500-second deadline. It
keeps the body in admission-process memory and the runner posts it to the
separate worker over actual loopback HTTP. The worker retains the production
OIDC dependency's header, audience, identity, and retry-count checks; its
Google verifier accepts one exact local token, so signature, issuer, and
expiry verification remain outside this gauntlet.

Scenarios cover:

1. fresh admission, rejected unauthenticated worker delivery, durable
   completion/readback, once-only fair-use meter, and terminal duplicate ACK;
2. failure after terminalization keeps staged material until a retry performs
   exact-job cleanup without reprocessing;
3. a pre-ledger failure returns the job to queue, then skips its durable
   processed-segment checkpoint without another STT call or fair-use charge;
4. a post-ledger failure returns the job to queue, then a later delivery
   converges the completed ledger without reprocessing;
5. a first pipeline success on the final Cloud Tasks delivery converges its
   completed ledger rather than publishing a false terminal failure;
6. retry-budget exhaustion becomes a truthful durable failure;
7. concurrent worker deliveries are fenced by the real Redis run lock;
8. a lost create-task acknowledgement converges through named-task
   `AlreadyExists`, never falls back inline, and later completes; and
9. a missing staged blob follows the real expired-input failure path without
   invoking STT.

Only external/provider leaves are replaced: Cloud Storage is local filesystem
storage, Cloud Tasks is the local strict recorder, Google OIDC verification
uses one exact local token, and VAD/STT/conversation processing are deterministic.
The gauntlet retains production PCM decoding, upload/staging ownership, task
protobuf construction, route authentication, locks, job/ledger transitions,
fair-use metering, status polling, and conversation persistence.

It does not prove real GCS, Cloud Tasks IAM/control-plane delivery,
Google-signed OIDC tokens, production VAD/STT/LLM quality, BYOK, or backfill
behavior. Those are distinct provider or product surfaces. With `--keep`, the
runner retains process logs, local staged files, and sanitized JSONL evidence;
evidence contains metadata only and rejects test UID/transcript sentinels. A
caller-supplied `--state-dir` is always preserved as well; relative paths are
resolved before child processes start.
