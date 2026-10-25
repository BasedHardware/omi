# Authenticated standalone-plugin transport

Owner: `utils/plugin_transport.py`. First consumer: the pCloud completion of
#20498; delivery problem and acceptance are tracked in #20213.

## Authority and composition

Authenticated `GET /v1/apps/{app_id}` decorates a deep copy of the app's setup,
home and completion URLs with per-account capabilities. Cached/public marketplace
records never receive them; owner edits strip launch credentials before storage.
The existing Flutter/macOS setup flows already use these fields and append the
same UID hint, so no new client-specific auth channel or mobile-only state store
is introduced. The plugin consumes setup nonces atomically and uses an HttpOnly
session plus CSRF-protected POST forms for mutations. A query UID never authorizes.
A launch grant is one-use and short-lived, so every client fetches fresh details
immediately before each home-page or authentication-step open instead of reusing a catalog or earlier
response: the Flutter app detail page (auto-open, the settings button and
post-install), the macOS and Windows app sheets, the Windows Apps page's first-time
Install, and the web app detail page.
Refresh failure never falls back to an earlier capability. Query-aware UID
helpers preserve signed query bytes, and late reads for a departed account or
page cannot launch the browser. Setup retries use the existing client owners,
not another authorization endpoint or parallel token cache.

Finalized conversation fanout preserves SSRF target pinning, privacy redaction,
the existing durable idempotency key and legacy apps. Only a registered app gets
a signed delivery header and conversation-scoped saved-audio capability. Its
existing webhook URL must match the trusted registration origin; metadata edits
cannot redirect a capability to a different host. Re-enabling an auto-disabled
registered app checks that origin and probes the service's non-mutating
`GET /health`, because the authenticated delivery endpoint rightly rejects the
unsigned empty `POST` legacy webhooks receive; deliveries stay signed.

The plugin durably admits a job before acknowledging delivery. Its persistent
store owns idempotency, per-file receipts, retry state, consent and connection
generation. It is not a new Omi conversation or audio source of truth. It reads
canonical saved audio through the existing playback path instead of attempting
to join uncorrelated live raw-audio callbacks. Missing audio is explicit.

`HEAD /v1/apps/{app_id}/backup-audio/{conversation_id}` rechecks current account
deletion, enabled-app availability and retained/unlocked/non-discarded conversation
ownership before a pending provider write. It does not inspect or enqueue audio.
`GET` applies the same checks and delegates the saved-audio manifest to
`utils/sync/playback.py`; it never accepts a caller-provided UID or download URL.
These are internal plugin-protocol endpoints, excluded from released-client SDKs.

## Wire protocol

Per-app HS256 JWTs use issuer `omi-plugin-transport/v1`, audience = app ID,
`sub` = authenticated UID, `iat`, `exp`, random `jti` and an exact `scope`:

| Scope | Lifetime | Binding |
| --- | --- | --- |
| `setup` | 10 minutes, consumed once | Registered HTTPS service and account |
| `status` | 10 minutes, repeatable read | Connected-state boolean for that account |
| `delivery` | 10 minutes | Account, POST path, canonical JSON SHA-256 |
| `audio` | 7 days maximum | Account and one conversation; fresh access checked on HEAD/GET |

Setup/status URL parameter: `omi_token`. Delivery header:
`X-Omi-Plugin-Authorization` (raw JWT). Canonical JSON is UTF-8 encoding of
`json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
allow_nan=False)`. The signed payload includes `_omi_backup_audio_token`.
Audio/access reads use `Authorization: Bearer <audio-scoped JWT>`.

The pCloud verifier is independently deployed and uses the same explicit wire
contract, tested against the actual backend signer. The models-only plugin SDK
is not expanded into an auth/worker framework. No unsigned fallback is accepted
by this new service. Old unregistered apps retain their existing behavior; this
does not retroactively secure all other plugins.

## Configuration and rollout boundary

`OMI_PLUGIN_TRANSPORT_JSON` is a **server-only secret**, mapping registered app IDs
to `base_url` and a distinct random `key` of at least 32 bytes. No value is
provisioned here. The pCloud service gets only its own app ID and key. Existing
backend runtime releases do not acquire a new required secret from this PR.
Before enabling a registration, its optional runtime binding must be reviewed
and provisioned across every host that executes finalized conversation fanout.
That deployment/configuration work is intentionally not performed by this
source-only task. The completion PR remains draft until the release checklist
is satisfied; do not merge an unsigned foundation first as a workaround.

Do not log capability-bearing URLs, header values, provider error bodies,
credentials or private payloads. The standalone app/proxy disable query access
logs. Signing-key rotation requires coordinated admission pause and handling of
outstanding jobs; encryption-key rotation is separate and tested in the plugin.

Architecture/implementation checklist and durable-storage topology:
[`plugins/omi-pcloud-app/README.md`](../../plugins/omi-pcloud-app/README.md).

## Verification ownership

The manifest-backed pCloud suite exercises real HTTP routing, cookie/CSRF/expiry,
body/account binding, durable partial success, consent, revocation and key rotation.
Backend tests exercise metadata copying, registered-origin restrictions, actual
fanout composition, legacy behavior and current access checks. These are
hermetic; live pCloud grant/callback and volume recovery verification belong to
the deploying operator. No live verification is implied by mocked provider IO.
