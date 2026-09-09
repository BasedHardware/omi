# Deployed entry increment

Development setup on 2026-09-07 created the isolated `based-hardware-dev`
PostgreSQL 18.4 instance and applied tested migrations 1–50. The application
login has only `omi_platform_application` membership, with neither superuser
nor RLS bypass; private database URL, codec and cursor secret versions are all
version 1. Credentials are outside source and OpenTofu state. The seven original runtime IAM grants and the transcription secret grant
remain unapplied because the operator cannot change project/secret IAM
or create the custom Firebase verification role. No Cloud Run service is live,
and schema installation alone does not release a database generation or mint
account/grant authority.

`bun run start:deployed` starts the existing Firebase/PostgreSQL memory process on
`0.0.0.0:$PORT`. `bun run check:deployed` is included in the v5 root `check` gate.
Build from this backend directory with
`docker build --platform linux/amd64 -t omi-platform-dev .`.

This increment serves authenticated canonical memory reads, task reads and
mutations, indexed device audio uploads, conversation reads, chat history
reads, granted main-chat session composition on the first conversation page, and Settings GET. All of them use the same database generation and Firebase authorization
configuration inside the readiness and shutdown boundary. Audio upload completion
does not certify transcription or conversation formation. Chat writes, generation
SSE, cancellation and attachments are explicit nested 404s without admission.
Settings identity/entitlement producers and authenticated MCP remain unavailable;
MCP returns 503. Missing `chat.read` is 403, not an empty
successful transcript. Signed-in Settings without a producer is 503, not a 200
profile invented from the Firebase token. This is not full backend parity or production qualification.

Required configuration:

| Variable                         | Authority                                                                                                                                                                 |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OMI_DATABASE_URL`               | Non-owner PostgreSQL login with `omi_platform_application` privileges; static credential or locally terminated authenticated connector, never migration-owner credentials |
| `OMI_FIREBASE_PROJECT_ID`        | Actual Firebase project whose tokens the deployed Admin adapter verifies with revocation checks and ADC                                                                   |
| `OMI_APPLICATION_ID`             | Persisted authorized application ID                                                                                                                                       |
| `OMI_DATABASE_GENERATION_DIGEST` | Exact released database generation, lowercase SHA-256                                                                                                                     |
| `OMI_CODEC_KEY_HEX`              | Stable secret, 32 bytes as lowercase hex                                                                                                                                  |
| `OMI_CURSOR_KEY_HEX`             | Independent stable signing secret, 32 bytes as lowercase hex                                                                                                              |
| `OMI_ACCOUNT_TIMEZONE`           | Explicit IANA timezone for this dev connection; per-account profile lookup remains unwired                                                                                |
| `OMI_LLM_GATEWAY_URL`            | HTTPS internal gateway, with `/v1/chat/completions` appended when absent                                                                                                  |
| `OMI_LLM_GATEWAY_SERVICE_TOKEN`  | Gateway service credential; no provider API key                                                                                                                           |
| `OMI_TRANSCRIPTION_API_KEY` | Service-owned Deepgram credential; never forwarded to the app |
| `OMI_TRANSCRIPTION_MODEL` | Explicit deployed model, such as `nova-3` |
| `OMI_MEMORY_RENDER_LANE`         | Provisioned `omi:auto:*` semantic lane supporting nonstream JSON completion; provider/model routing remains gateway-owned                                                 |
| `PORT`                           | Listener port; defaults to 8080                                                                                                                                           |

The runtime rejects Auth emulator configuration and missing keys. Secrets are
injected by the release environment, never baked into the image. Keys must
survive revision replacement. There is no automatic account creation, grant,
cutover, schema migration, or generation release at service startup.

`/health` means the process is alive. `/ready` only succeeds after the existing
sealed readiness proof verifies PostgreSQL **18.4**, the entire checksummed
migration manifest, and the configured released generation. PostgreSQL 18
major-version support alone does not satisfy that proof. Firebase project
bindings, account control, lifecycle, grants, and graph content are independently
rechecked by the existing authorized read path.

## Database operator sequence

Provision the existing NOLOGIN roles `omi_platform_application`,
`omi_platform_cleanup`, `omi_platform_restore`, and
`omi_platform_restore_operator` before migrations. The runtime login must be a
non-owner member of only the application role with inherited privileges. The
migration owner and restore operator are separate credentials. Do not grant
application credentials direct ledger/control table access.

Run the existing checksummed migration runner from `drivers/postgres`, with
`OMI_MIGRATION_DATABASE_URL` supplied privately to the operator process:

```sh
bun -e 'import postgres from "postgres"; import {runPostgresMigrations} from "./migrations/runner"; const url=process.env.OMI_MIGRATION_DATABASE_URL; if(!url)throw Error("missing migration credential"); const sql=postgres(url,{max:1}); try { const result=await runPostgresMigrations(sql); console.log(JSON.stringify(result)); } finally { await sql.end(); }'
```

Migration installation does not release a generation. The existing controlled
flow is a persisted restore/checkpoint candidate, verified checkpoint evidence,
then `omi_memory.release_postgres_restore_generation_v2` under the
`omi_platform_restore_operator` role. Its seven parameters are the database
generation digest, expected checkpoint revision, checkpoint content hash,
candidate digest, evidence digest, new release revision, and release content
hash. Supply the actual verified operator receipts; do not copy the qualification
test's repeated-character digests or insert a `released` row manually. A new dev
database still needs that existing admission flow before readiness can open.

Account control, credential issuance, and capability grants need authoritative
producers; this repository currently has no deployed producer for those records.
ADR-010 keeps initial account control in the legacy origin: a verified Firebase
identity cannot create or activate an account or grant itself a capability.
`prod-local-identity-seed` and the SQLite demo seed are local QA tools, not a
deployed bootstrap procedure.

The bounded binding command links a real Firebase identity to **existing** current
active account/control/credential/grant records. It creates only the two immutable
Firebase binding rows from migration 0012; it cannot bootstrap missing authority.
Run with a separate operator database credential that can inspect the authority
rows and insert bindings, never the ordinary application login. Keep the ID token,
operator URL, manifest, and receipt private. The deployment identity must have
Firebase Admin revocation-check access and must not use an Auth emulator.

```sh
bun run bind:firebase /private/binding.json /private/firebase-id-token /private/new-receipt.jsonl
```

Supply `OMI_BINDING_OPERATOR_DATABASE_URL` privately. The manifest has exactly
`projectId`, `uid`, `accountId`, `principalId`, `applicationId`, `credentialId`,
`controlRevision`, `controlHash`, `credentialHash`, `grantHash`, `expiresAt`, and
`reasonRef`. The three hashes must match the authoritative persisted revisions;
`expiresAt` is Unix seconds within the next fifteen minutes. The pinned grant is
`memories.read`. The command verifies the token's exact project/UID and revocation,
locks current authority in a serializable transaction, and rejects missing,
expired, inactive, revoked, conflicting, or changed records. Exact replay returns
`unchanged`; existing bindings to any other coordinates fail rather than being
silently ignored. No authority records or credential secrets are created.

The required receipt path is created exclusively with mode 0600. An fsynced intent
records the manifest digest before mutation, followed by a result. Archive the
manifest and receipt in the operator's durable audit store. If the process dies or
result persistence fails after commit, an intent without a terminal result (or
`reconcile_required`) requires exact-state reconciliation before retrying. This
command does not provision operator IAM/database roles or the missing authoritative
issuance producer.

## Current limits and remaining qualification

The entry admits two simultaneous domain requests with a four-connection pool
and a 2-MiB HTTP body ceiling; individual routes enforce their smaller limits.
Ordinary requests have a shared 25-second cancellation budget; explicit transcription has 135 seconds for the bounded 120-second provider call and persistence. Cancellation propagates through the
PostgreSQL authority transactions and gateway fetch/body consumption. Gateway
requests also enforce 256-KiB input/output limits. Invalid or ungrounded citations
fail the read. Accepted and STM coverage remain explicitly unavailable.

Migration 0046 persists validated grounded model responses in the existing
product-projection ownership and deletion surface. Cache keys bind the account,
authorized graph projection, reader, render input, and every renderer version.
Every read and publication rechecks the existing sealed account/grant/epoch
transaction authority. Concurrent producers use the first committed response;
subsequent processes regenerate genuine branded render nodes from that response.
Completed nodes survive a later request timeout without certifying a partial page.
The same snapshot and renderer versions therefore retain stable continuation
content across requests and process replacement. Model or graph changes invalidate
that reuse. Account deletion includes these rows in product-projection cleanup.

The generic gateway JSON contract, supported semantic lane, real model output,
Cloud SQL patch version, deployed Firebase identity, and actual non-empty graph
must be exercised before claiming live memory functionality. The existing
process drain closes admission first; the executable imposes an eight-second
shutdown deadline. Exact Linux image/Node control qualification, content-safe
operational trace delivery, and full product-route parity remain outstanding.

Authenticated conversation projection and cursor rules are documented in [deployed conversation reads](conversations-deployed.md).
