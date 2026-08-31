# Local listen → pusher stack gauntlet

Run this explicit, local-only gauntlet when changing the listen WebSocket,
`ListenPusherSession`, pusher opcode handling, or finalization lifecycle:

```bash
backend/testing/listen_pusher_stack/run.sh --keep
```

Prerequisites are the backend virtual environment (`backend/scripts/sync-python-deps.sh`),
the root Node dependencies (`npm ci`), Redis, and Java 21+. The runner discovers
Homebrew's `openjdk@21` automatically when `java` is not already on `PATH` and
chooses a per-run Firestore emulator port, so it does not conflict with shared
developer services.

It starts an isolated Redis and local ASGI processes while Firebase's command
owns a fresh Firestore emulator. The inline scenarios use the real backend,
pusher, and Parakeet stub; durable scenarios start separate real listener and
finalization-worker processes with a strict loopback Cloud Tasks client:

```text
native /v4/listen client → real backend → real pusher
                               ↘ real Parakeet WS client → local protocol stub

real listener admission → real tasks_v2.Task → strict loopback task record
                                                   ↘ separate real finalization worker route
```

The child-process environment is allowlisted: it has a private empty
`HOME`/cloud config directory and receives no provider credentials, developer
proxies, ADC configuration, or production project settings. The harness also
rejects a non-loopback Firestore endpoint.

The test deliberately exercises the production listen runtime (`main:app`),
real pusher router, binary frames 101/102/103/104/201, Firestore finalization
jobs, leases, fanout admission/idempotency, recording-session binding,
reconnect code, and the real Cloud Tasks finalization handler.
It seeds private-cloud mode only to make the real 103 + 101 audio frames flow;
the provider/storage leaves are disabled because this harness has no cloud
credentials.

The Cloud Tasks entrypoint replaces only provider-side leaves below the real
processing persistence and memory safety fence:

- conversation summary generation;
- canonical memory provider/store work after `MemoryService.ensure_canonical_mutation_ready`;
- external-integration delivery.
- other credentialed derived effects such as vector writes and webhooks.

The inline pusher entrypoint retains its older whole-processing and memory
mocks for protocol/lifecycle race scenarios. Those scenarios are explicitly
protocol evidence, not memory-safety evidence. The mandatory Cloud Tasks path
sets `MEMORY_ENABLED=on`, executes the production parser and fence, then proves
the post-fence leaf runs. A negative scenario unsets the flag and proves the
durable job stays retryable, the post-fence leaf does not run, and the bounded
`memory_fence` diagnostic is emitted without identifiers.

Private-cloud audio storage is also local-only; the queue and 101/103 frame
handling remain real.

The real finalizer still persists through the lifecycle owner and claims and
completes durable fanout. Inline pusher scenarios also send the real pusher
result frame. In durable mode, production code builds the real `tasks_v2.Task`;
the strict local client
accepts only its opaque `{job_id, dispatch_generation}` payload, a loopback
HTTP handler URL, expected OIDC audience/service account, and the production
dispatch deadline. The harness replaces only OIDC signature verification with
a local bearer token, while the production FastAPI dependency and retry-count
header remain in the request path.

It does not prove LLM/vector output quality, GCS delivery, downstream
integration delivery, Cloud Tasks IAM provisioning, or Google OIDC signature
verification. Trace files record durable IDs, frame metadata, and byte counts,
never audio or transcript text.

Scenarios:

1. audio → one bounded live-STT accepted attempt → streaming segment → one matching successful terminal (including after teardown replay) → stale live-session lifecycle → persisted content → completed inline job;
2. completed native UUID reconnect replays the terminal binding without a new job;
3. a stale empty desktop recording is removed by the next-session lifecycle path and creates no job;
4. a pusher process loses the first 104 before claim, is restarted, and the
   live backend session replays the same job ID and dispatch generation exactly once.
5. source close immediately after the inline opcode-104 handoff waits until the
   pusher connection cleanup has run, then proves the already-claimed durable
   finalizer still completes without a later listen session;
6. concurrent public `POST /v1/conversations/{id}/finalize` retries produce one
   opaque named task and one outbox job, prove the `AlreadyExists` boundary,
   then survive listener restart before the detached worker completes and safely
   ACKs a duplicate delivery. A bounded test-entrypoint read barrier makes the
   intended stale-read race deterministic without replacing the route,
   lifecycle transaction, or task construction;
7. a session closes during the deferred pending-finalization window; the real
   recovery path from #9960 enqueues one opaque Cloud Tasks task, then a real
   worker retry preserves `processing` until it completes the same job;
8. a worker exhausting its two-attempt test budget atomically dead-letters the
   job with `terminal_outcome=failure` and marks the still-current conversation
   `failed`/`discarded`, while a later duplicate delivery is fenced;
9. an integration failure after processing retries only durable fanout, never
   re-runs completed conversation processing.
10. in `RECORDING_SESSION_MODE=enforce`, one operation-scoped `completed`
    envelope write fails before Firestore, emits no matching client event, and
    leaves the durable phase/sequence at `processing`/`1`; a fault-free
    same-controller retry, released only after those assertions, then persists
    `completed`/`2` and emits exactly one matching sequenced event;
11. `shadow` and `dual_write` repeat the same selected write failure and prove
    only their documented unsequenced legacy compatibility event is emitted,
    while the durable phase/sequence remains `processing`/`1`.

The fault capability exists only in the harness listener entrypoint. Its
`OMI_STACK_RECORDING_LIFECYCLE_FAULT` value is an exact JSON selector containing
`uid`, `recording_session_id`, `conversation_id`, and `phase`; the matching
write is failed once and only once. Production starts `main:app` directly and
does not import this selector. The Phase 0A offline-sync replay harness does not
consume this seam; later streaming replay work can opt into the listener
entrypoint and operation selector.

Inline source-close coverage uses a file-gated local provider leaf only to make
the post-claim timing deterministic. It retains the real listener, pusher
router, Firestore claim/completion, and connection cleanup paths.

This complements, rather than replaces, the storage race test:

```bash
npm run test:listen-lifecycle:emulator
```

It intentionally does not test real Parakeet inference, LLM/vector quality,
GCS, or external integration delivery.  Those require their own environment
and should not turn this deterministic local failure test into a credentialed
integration suite.
