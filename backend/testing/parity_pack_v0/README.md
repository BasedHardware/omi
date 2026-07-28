# Parity Pack v0

This is a local replay-pack contract, not a production capture path. Pack payloads
are restricted local/dev artifacts and must never be committed.

## Dev capture gate

Future capture callers must instantiate `CaptureWhitelist.from_environ()` and
call `allows(principal_id)` before serializing any cassette bytes. It defaults to
deny. A capture is permitted only with all three settings:

```bash
OMI_ENV=dev
OMI_PARITY_PACK_CAPTURE=1
OMI_PARITY_PACK_ALLOWED_PRINCIPALS='synthetic-user-1,synthetic-device-2'
```

Use anonymous session/event identifiers in `CassetteIdentity`. Request
fingerprints are SHA-256 digests of canonical redacted request structure; auth,
cookies, keys, signed URL parameters, and best-effort email/phone strings are
removed or masked before the digest is generated. Do not put raw request data in
manifests, reports, or Git.

## Layout

```text
<restricted-local-pack>/
  manifest.json                 # hashes + case descriptors only
  inputs/<case>.json            # referenced by inputs_ref
  cassettes/<identity-key>.json # referenced by cassette_refs
```

`manifest.json` records the schema version, artifact hashes, input/cassette
references, expected outcomes, and invariant IDs. Run the foundation checks with
`npm run test:parity-pack-v0`.

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
