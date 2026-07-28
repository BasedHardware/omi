# Parity Pack v0 foundation

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
