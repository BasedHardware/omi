# Support harness

The private harness exposes two GET routes for a support person's own Firebase
ID token. It makes no account changes. Each successful request must append a
`support_audit_log` document before returning; failed audit persistence returns
503 with no account or trace data.

## CLI

Support people do not get a GCP key. From a checkout of this repo:

```bash
scripts/omi-support login
scripts/omi-support whoami
scripts/omi-support lookup customer@example.com
scripts/omi-support trace customer@example.com --from 2026-10-01T00:00:00Z --to 2026-10-02T00:00:00Z
```

`login` opens a localhost page and uses the same public Firebase web config as the app (`config/public-build-values.json`, prod). `localhost` is an authorized Firebase auth domain. Sign in with the support person's Omi Google account, not the customer's. The CLI stores only the Firebase refresh token at `~/.config/omi-support/session.json` (mode 0600) and refreshes a short-lived ID token per command.

`whoami` prints the Firebase uid. An operator with Firestore write then creates `supportData/{that uid}` with `role: support:read` and an optional future `expires_at`. Until that document exists, lookup and trace return 403. This CLI cannot create the grant.

`--base-url` defaults to `https://api.omi.me`. The routes are not served until this backend change is deployed. A missing conversation row does not prove where a recording was lost. Discarded or deleted rows stay in the trace as captured/synced evidence and are not reported as saved.

## Access

An authorized operator manages `supportData/{caller_uid}` outside this API.
The document must exist with `role` exactly `support:read`. Optional `expires_at`
must be a timezone-aware Firestore timestamp in the future; null, naive,
malformed, and expired values deny access. This implementation creates no grants.

Use `Authorization: Bearer <Firebase ID token>` for the support caller.
`ADMIN_KEY`, `X-Admin-Key`, `adminData`, and caller-supplied admin UID headers do
not authorize these routes. Authentication performs no last-active writes for
either the caller or the customer. Missing/invalid tokens return 401, denied
grants return 403, and unavailable authorization storage returns 503.

## Requests

Supply one exact email, normalized by trimming whitespace and lowercasing.
Empty, malformed, comma-separated, and wildcard queries return 422. An unknown
email returns a generic 404. There is no list-users or fleet-search route.

```text
GET /v1/support/lookup?email=customer%40example.com
GET /v1/support/trace?email=customer%40example.com&from=2026-10-01T00%3A00%3A00Z&to=2026-10-02T00%3A00%3A00Z
Authorization: Bearer <caller Firebase ID token>
```

Lookup returns UID, normalized email, plan, optional activity timestamp/platform,
current UTC calendar-month transcription usage from the existing hourly usage
meter, optional limit/remaining seconds, and fair-use stage alone. Missing
subscription defaults and legacy plan normalization are read-only. A null limit
or remaining value means unlimited or unknown; finite zero remains zero.

Trace requires timezone-aware ISO-8601 `from` and `to`, with a positive window
of at most seven days. Bounds are inclusive on `started_at`. It reads at most
51 conversation documents to detect truncation, returns at most 50 newest-first
rows, and includes discarded/deleted documents as server-side capture evidence.
The reader selects lifecycle timestamps/status, audio-file metadata, and the
existing `transcript_segments_compressed` storage marker. It never reads transcript
payloads. It does not decrypt/decompress transcripts,
hydrate photos, download audio, or query logs. Stored compressed/encrypted
transcript presence indicates stored bytes, not verified readable text (an encoded
empty list also has stored bytes). Legacy unmarked transcripts conservatively
report `has_transcript=false`; that value cannot prove absence on those documents.

Every document counts as captured and synced. Processed means postprocessing
completed, or conversation completed with postprocessing absent/not_started/
completed. Saved requires processed plus conversation completed, and is false when `discarded` or `deleted` is set. Those flags are returned as booleans. Failed reflects
either failed status. Failure stage is process unless postprocessing completed
but conversation failed, in which case it is save. These are lifecycle
inferences, not proof of an on-device capture/sync failure: a missing server
row cannot establish where a recording was lost. Duration comes from finished
minus started timestamps when available. Audio presence requires a nonempty
`audio_files` list. The pure projection also accepts already-loaded nonempty
transcript/segments fields, but the server reader uses only the storage marker.
Only booleans leave the route, never those objects.

## Privacy and audit

Responses use strict allowlist models. No phone, display name, Stripe/provider
identifiers, transcript text, notes, memories, summaries, photos, free-text
errors, audio paths/URLs/buckets/fingerprints, or feedback context are returned.
The audit contains caller UID, action, target UID, SHA-256 hex of the normalized
email, a server timestamp, and the trace's UTC bounds where applicable. It does
not contain the raw email, bearer token, or customer content. The API does not
log those values. Configure ingress/access logs to avoid recording raw query
strings, which contain the requested email.

Both routes are excluded from OpenAPI and the public/app/integration contract
exports. There are no support writes, grant-creation endpoints, or client SDK
changes. The backend's normal deployment process ships this code; this runbook
makes no deployment or grant changes.

## Local verification

From this worktree's `backend` directory, with no live GCP:

```bash
PATH=/opt/homebrew/bin:$PATH ./.venv/bin/python -m pytest tests/unit/test_support_harness.py -q
```

The tests use mocked Firebase auth and an in-memory Firestore boundary. They
exercise both GET routes, auth/expiry/admin-key rejection, response privacy,
read-only defaults/migrations, masked bounded reads without content hydration,
lifecycle projection, private schema exclusion, and mandatory audit failure.
