# Security Model

Ambient Second Brain Controller never records audio and never calls Android microphone APIs. The Omi Android app owns capture, private mode, foreground notifications, local WAL/spool storage, and all local overrides.

## Policy Signing

- The plugin issues short-lived Ed25519-signed policies.
- Default policy validity is 10 minutes.
- The Android app pulls `/capture/policy/current`, verifies the signature locally, and enforces local user settings before capture changes take effect.
- Policy payloads are signed as canonical JSON. The endpoint returns that exact JSON string as `payload`, plus a `structured_payload` copy for debugging.

## Fail-Closed Rules

The plugin refuses to issue policy for revoked or unknown devices. It also defaults conservatively:

- capture mode is `off`
- accessibility is disabled
- raw audio upload is disabled
- telemetry text is disabled

If the user disables capture, issued policy uses `capture_mode=off` and `allow_foreground_mic=false`.

## Privacy Boundaries

- Telemetry rejects audio fields and rejects transcript/text fields unless `allow_telemetry_text` is enabled.
- Fallback segments retain `source`, health, degraded, and raw-audio-availability metadata.
- Fallback text is never relabeled as normal audio transcript.
- The plugin never promises call recording. Communication mode means call/meeting awareness and optional mic attempts where Android permits.

## Key Material

Set:

- `AMBIENT_POLICY_PRIVATE_KEY`: Ed25519 private key as base64 raw seed, DER, or PEM.
- `AMBIENT_POLICY_PUBLIC_KEY`: Ed25519 public key as base64 DER, raw, or PEM.
- `AMBIENT_POLICY_KEY_ID`: stable key id advertised to Omi and Android.

For development only, the app generates a deterministic local key if no key is configured. Do not use that fallback in production.
