# Backend Worker (Cloudflare staging)

`apps/backend-worker` is the Cloudflare-native staging backend for the v5
clients: a Hono Worker serving Firebase-authenticated `/v1/*` APIs over D1,
R2, Queues, Workers AI, and a per-account Durable Object. Area guide:
[`apps/backend-worker/AGENTS.md`](../apps/backend-worker/AGENTS.md). This doc
covers the architecture facts; the guide covers day-to-day work.

## Storage and coordination split

- **D1 is authoritative** for the migrated tasks projection and
  device-session metadata (`migrations/0001_tasks.sql`,
  `0004_device_sessions.sql`, `0010_account_scoped_ids.sql`; logic in
  `src/tasks.ts`, `src/device-sessions.ts`).
- **Capture bytes** go to the bound `ATTACHMENTS` R2 bucket with an indexed
  per-packet hash/acknowledgment ledger (`0007_device_audio_chunks.sql`);
  uploads require a stable zero-based `chunkIndex`, a native-minted
  `createRecordingId` capture ID (`0008`), and replay-safe metadata
  (`0009`).
- **Durable Objects coordinate per-account admission and
  generation/event sequencing only** — the `AccountBackend` DO serializes D1
  admissions across external database awaits so parallel requests cannot
  exceed the chat limit and simultaneous retries return the same generation.
- **LLM traffic is fail-closed** behind the Cloudflare AI Gateway/OpenRouter
  adapter (`src/openrouter.ts`) when gateway mode is enabled
  (`OPENROUTER_GATEWAY_ENABLED === "true"`); no direct provider credential
  or Google backend is part of this path. Staging defaults to disabled.
- **Workers Observability** emits correlation-safe request events
  (`src/observability.ts`); sink modes and failure events are policy-tested.

## Transcription and canonical authority

- Transcription runs from verified audio completion through durable D1 jobs
  (`0006_device_transcriptions.sql`) and Workers AI
  (`@cf/openai/whisper-large-v3-turbo`) into the app: one job claimed per
  minute, 15-minute lease, ≤5 attempts; audio stays in R2 on failure.
- Canonical memory reads and task reads/writes use the optional
  authenticated `CANONICAL_SERVICE` service binding
  (`src/canonical-service.ts`). It is intentionally not declared in
  `wrangler.jsonc`: without it, `/v1/memories` fails closed
  (`projection_unavailable`) and D1 task reads remain. The target must
  independently validate the Firebase bearer. Production task authority
  still needs provisioning.

## Desktop sign-in handoff

Migration `0011_desktop_auth.sql` + `src/desktop-auth*.ts` back
`/v1/auth/desktop/{start,complete,exchange}` and the `/auth/desktop`
confirmation page: derived session IDs, SHA-256-only storage, 5-minute
sessions, single-use exchange minting an RS256 Firebase custom token. These
routes are mounted before the `/v1/*` authorization middleware by design —
the handoff is how a caller earns Firebase credentials.

## Delivery gate

Releases follow `apps/backend-worker/RELEASE.md`: verify migrations through
the operator evidence endpoint, then deploy, then verify `${STAGING_WORKER_URL}/ready`.
Rollback lives in `ROLLBACK.md` (`wrangler versions rollback`; note the
no-rollback boundary on the first release). CI (`backend-worker-staging`
job) refuses to deploy when migration evidence is missing or mismatched.

**Apply migrations remotely only after reading `RELEASE.md`.** The migration
set is 0001–0011 (tasks, chat, attachments, device sessions, uploads,
transcriptions, audio chunks, capture ID, capture time, account-scoped IDs,
desktop auth). Several are coordinated client+Worker releases (0007, 0008)
or forward-only rebuilds (0010) — the runbook spells out per-migration
warnings, and `migrations/manifest.ts` pins exact migration bytes, so
applied migration files must never be edited.

## Local commands

From `apps/backend-worker/` (see the AGENTS.md for the full list):
`bun run dev`, `bun run test` (bun-test contract layer + vitest-pool-workers
integration layer against miniflare), `bun run deploy:dry-run`,
`bun run verify:ready|release|migrations`. Prefix wrangler invocations with
`WRANGLER_SEND_METRICS=false`. Secrets are provisioned only through
`wrangler secret put` — never in repository files.
