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

The pusher entrypoint (for inline scenarios) and the Cloud Tasks entrypoint
(for durable scenarios) replace only these provider-side leaves:

- conversation LLM processing;
- memory extraction;
- external-integration delivery.
- private-cloud audio storage (the queue and 101/103 frame handling remain real).

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

1. audio → streaming segment → stale live-session lifecycle → persisted content → completed inline job;
2. completed native UUID reconnect replays the terminal binding without a new job;
3. a stale empty desktop recording is removed by the next-session lifecycle path and creates no job;
4. a pusher process loses the first 104 before claim, is restarted, and the
   live backend session replays the same job ID and dispatch generation exactly once.
5. concurrent public `POST /v1/conversations/{id}/finalize` retries produce one
   opaque named task and one outbox job, prove the `AlreadyExists` boundary,
   then survive listener restart before the detached worker completes and safely
   ACKs a duplicate delivery. A bounded test-entrypoint read barrier makes the
   intended stale-read race deterministic without replacing the route,
   lifecycle transaction, or task construction;
6. a session closes during the deferred pending-finalization window; the real
   recovery path from #9960 enqueues one opaque Cloud Tasks task, then a real
   worker retry preserves `processing` until it completes the same job;
7. a worker exhausting its two-attempt test budget atomically dead-letters the
   job and marks the still-current conversation `failed`/`discarded`, while a
   later duplicate delivery is fenced;
8. an integration failure after processing retries only durable fanout, never
   re-runs completed conversation processing.

The inline compatibility coverage deliberately triggers stale live-session
finalization before closing. A source close immediately after opcode 104 takes
a different inline/BYOK cancellation path, tracked in #9995; only the detached
Cloud Tasks scenarios assert clean-close durability.

This complements, rather than replaces, the storage race test:

```bash
npm run test:listen-lifecycle:emulator
```

It intentionally does not test real Parakeet inference, LLM/vector quality,
GCS, or external integration delivery.  Those require their own environment
and should not turn this deterministic local failure test into a credentialed
integration suite.
