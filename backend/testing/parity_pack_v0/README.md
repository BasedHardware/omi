# Parity Pack v0

This is a local replay-pack contract, not a production capture path. Pack payloads
are restricted local/dev artifacts and must never be committed.

## Dev capture gate

`CaptureTap` uses `CaptureWhitelist.from_environ()` and calls
`allows(principal_id)` before serializing any cassette bytes. It defaults to
deny. A capture is permitted only with all three settings:

```bash
OMI_ENV_STAGE=dev
OMI_PARITY_PACK_CAPTURE=1
OMI_PARITY_PACK_ALLOWED_PRINCIPALS='synthetic-user-1,synthetic-device-2'
```

Use anonymous session/event identifiers in `CassetteIdentity`. Request
fingerprints are SHA-256 digests of canonical redacted request structure; auth,
cookies, keys, signed URL parameters, and best-effort email/phone strings are
removed or masked before the digest is generated. Do not put raw request data in
manifests, reports, or Git.

`CaptureTap.start()` creates one invocation under that anonymous identity. Its
`observe()` boundary records client, outbound provider, and inbound provider
wire observations using relative milliseconds. A whitelist miss writes no
cassette bytes and retains only bounded lane/reason metadata.

## Live surface wiring

The `/v4/listen` runtime creates `routers.listen.parity_capture.ListenParityCapture`
only after Firebase WebSocket authentication and STT provider selection. It uses
the Firebase UID solely for the exact `CaptureWhitelist` comparison, derives
anonymous session/event identifiers before cassette creation, and records decoded
client audio, the successful STT socket send, and provider transcript callbacks.
The capture persists during normal listen-session teardown.

Set a fourth, required operator-only variable to an absolute path outside the
repository:

```bash
OMI_PARITY_PACK_ROOT=/absolute/restricted/local/parity-pack
```

There is no default root. A missing, relative, or repository-contained root is
disabled; `OMI_ENV_STAGE` other than `dev`, a missing `OMI_PARITY_PACK_CAPTURE=1`,
or an allowlist miss is also disabled. No Helm or production default enables this
path. The local cassette may include restricted audio/transcript event payloads,
so keep its root outside Git and never attach it to a PR.

`SurfaceParityCapture` uses the same gate/exporter for the additional
memory-forming surfaces below.  It extends the cassette document with optional
top-level discriminators while leaving the v1 identity, fingerprint, and event
contract unchanged for existing players:

| `surface` | `source` | Captured seam |
| --- | --- | --- |
| `ptt` | `desktop_ptt_http`, `desktop_ptt_stream` | Desktop PCM PTT and live PTT STT (bounded audio + transcript events) |
| `screen` | `desktop_screen_activity_sync` | Text-only screen activity/context sync; no video or embedding vectors |
| `conversation_finalization` | `conversation_<source>` | Transcript input, memory extraction result, and accepted memories |
| `memory_write` | `v3_memory_create`, `v3_memory_batch_create`, `integration_<app>`, `twitter_<persona>` | Manual/API, integration, and social memory writers |
| `memory_import` | `v3_memory_import_batch` | Bounded import artifacts and ingestion result (not raw media) |

The development listen deployment mounts `/var/omi-parity-pack` as an `emptyDir`
for explicitly allowlisted dogfood principals and best-effort exports cassette
JSON to a private development bucket:

```text
gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0/cassettes/<identity-key>.json
```

Export is fail-open (listen continues if GCS is down). Download for offline
replay:

```bash
gcloud storage cp -r \
  "gs://based-hardware-dev-omi-parity-pack-v0/parity-pack/v0" \
  ./omi-parity-pack-dogfood/
# Point OMI_PARITY_PACK_ROOT at the local tree (or compose a pack with
# manifest.json as required by this README), then:
npm run test:parity-pack-v0
```

Never promote cassettes to production storage or commit them to the repository.
The emptyDir scratch is still lost on pod restart before a successful export.

Dev listen capture exposes the zero-initialized
`omi_parity_pack_capture_events_total{stage,outcome,reason_class}` counter and a
matching `parity_pack_capture_event` log marker. The closed labels distinguish
accepted listens, allowlist decisions, capture initialization, cassette
persistence, and GCS export attempt/success/failure. These events never include
principal or session identifiers, payloads, credentials, or cassette object
paths; non-dev runtimes do not increment or log them.

## Replay players

`STTCassettePlayer` and `LLMCassettePlayer` are callback-oriented loopback
adapters for the wire-oracle fakes. Give both the shared ordered
`InvocationTopology`; `play()` verifies complete identity and canonical
redacted request fingerprint, then yields recorded events and relative
`dt_ms`. `assert_complete()` fails unused cassettes; a mismatch, wrong order,
or an extra call fails immediately. Cassettes remain restricted local/dev
inputs and must not be committed.

## Layout

```text
<restricted-local-pack>/
  manifest.json                 # hashes + case descriptors only
  inputs/<case>.json            # referenced by inputs_ref
  cassettes/<identity-key>.json # referenced by cassette_refs
```

`manifest.json` records the schema version, `pack_id`, artifact hashes, and one
entry per case: input/cassette references, expected outcomes, invariant IDs, the
anonymous cassette identity, and the redacted request fingerprint (digest only).
Run the foundation checks with `npm run test:parity-pack-v0`.

## Gold, drift, and rewrite slot

`double_run_gold()` runs every case twice before a gold update. It rejects a
nondeterministic result; `write_gold=True` is the only way it changes
`expected_outcomes`. Ordinary replay produces a digest-only, **warn-only**
drift report, so drift never masks a result or blocks a developer investigation.

`rewrite_launch_descriptor()` is the explicit integration slot for a future
rewrite binary. The descriptor is intentionally unavailable in this repository:
operators must install and invoke the approved binary themselves rather than
having replay download or execute one.

The synthetic v0 matrix names six overlays: `baseline`, `duplicate_delivery`,
`provider_timeout`, `provider_error`, `out_of_order_events`, and
`redacted_capture`. They contain no captured payloads.

## Operator workflow (dev only)

1. Keep the local pack outside this repository. Never commit cassettes, inputs,
   payloads, or a whitelist.
2. Set `OMI_ENV_STAGE=dev`, `OMI_PARITY_PACK_CAPTURE=1`, and an explicit
   `OMI_PARITY_PACK_ALLOWED_PRINCIPALS` allowlist. Any other stage or a missing
   allowlist is deny-by-default and persists no cassette bytes.
3. Run the application path with the opted-in synthetic/dev principal, then run
   `npm run test:parity-pack-v0` to replay hermetically. The tests deny egress
   and require fake-hit accounting; no provider or production service is used.
