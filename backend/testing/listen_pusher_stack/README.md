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

It starts an isolated Redis and three local ASGI processes while Firebase's
command owns a fresh Firestore emulator:

```text
native /v4/listen client → real backend → real pusher
                               ↘ real Parakeet WS client → local protocol stub
```

The child-process environment is allowlisted: it has a private empty
`HOME`/cloud config directory and receives no provider credentials, developer
proxies, ADC configuration, or production project settings. The harness also
rejects a non-loopback Firestore endpoint.

The test deliberately exercises the production listen runtime (`main:app`),
real pusher router, binary frames 101/102/103/104/201, Firestore finalization
jobs, leases, fanout admission/idempotency, recording-session binding, and
reconnect code.
It seeds private-cloud mode only to make the real 103 + 101 audio frames flow;
the provider/storage leaves are disabled because this harness has no cloud
credentials.

The pusher entrypoint replaces only these provider-side leaves:

- conversation LLM processing;
- memory extraction;
- external-integration delivery.
- private-cloud audio storage (the queue and 101/103 frame handling remain real).

The real finalizer still persists through the lifecycle owner, claims and
completes durable fanout, and sends the real pusher result frame. It does not
prove LLM/vector output quality, GCS delivery, or downstream integration
delivery. Trace files record frame metadata and byte counts, never audio or
transcript text.

Scenarios:

1. audio → streaming segment → persisted content → close → durable completed job;
2. completed native UUID reconnect replays the terminal binding without a new job;
3. a stale empty desktop recording is removed by the next-session lifecycle path and creates no job;
4. a pusher process loses the first 104 before claim, is restarted, and the
   live backend session replays the same job ID and dispatch generation exactly once.

This complements, rather than replaces, the storage race test:

```bash
npm run test:listen-lifecycle:emulator
```

It intentionally does not test real Parakeet inference, LLM/vector quality,
GCS, or external integration delivery.  Those require their own environment
and should not turn this deterministic local failure test into a credentialed
integration suite.
