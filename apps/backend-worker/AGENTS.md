# Backend Worker (Cloudflare) — Developer Guide

Inherits the root [`../../AGENTS.md`](../../AGENTS.md) rules (Bun only, no
secrets in files, `bun run check` before commit). This is the Cloudflare-native
staging backend: Hono Worker + D1 + R2 + Queues + Workers AI + a per-account
Durable Object. Architecture narrative:
[`../../docs/backend-worker.md`](../../docs/backend-worker.md); release
runbook: [`RELEASE.md`](RELEASE.md); rollback: [`ROLLBACK.md`](ROLLBACK.md).

## File map

```
src/index.ts            # fetch/scheduled/queue entry, env typing
src/http-core.ts        # /v1 route assembly, R2 attachment plumbing, /ready
src/account.ts          # AccountBackend Durable Object: admission, generation lifecycle
src/chat.ts, wire.ts, generation-prompt.ts   # D1 admissions, wire types, prompt bounds
src/openrouter.ts       # AI Gateway/OpenRouter adapter (fail-closed)
src/device-sessions.ts  # capture sessions: open/append/complete (D1 + R2 ledger)
src/device-transcriptions.ts  # durable transcription jobs (claim/lease/retry)
src/canonical-service.ts      # optional CANONICAL_SERVICE proxy (memories/tasks)
src/desktop-auth*.ts, desktop-glance.ts   # desktop sign-in handoff + confirmation page
src/observability.ts    # correlation-safe events, sink modes
migrations/             # 0001–0011 SQL + manifest.ts (pins exact bytes)
test/                   # bun-test contract layer + vitest-pool-workers integration layer
scripts/                # verify-ready.ts, verify-release.ts, verify-migrations.ts, dev-elysia.ts
wrangler.jsonc          # staging config (D1, R2 ATTACHMENTS, DO, queue, AI, cron)
wrangler.test.jsonc     # test-only config for vitest-pool-workers
```

## Invariants

- D1 is authoritative for the tasks projection and device-session metadata;
  R2 (`ATTACHMENTS` binding) holds capture bytes behind the indexed
  hash/ack ledger. Applied migration files are immutable
  (`migrations/manifest.ts` pins bytes; `test/migrations.verify.test.ts`
  and the remote evidence preflight enforce it).
- The DO serializes D1 admissions across external awaits; generation
  prompts are bounded (40 messages / 32 KiB) and account-scoped.
- LLM calls fail closed: gateway mode requires
  `OPENROUTER_GATEWAY_ENABLED === "true"` plus an exact `openrouter.ai`
  https gateway URL; every failure maps to a wire error, never a raw
  provider passthrough. Staging default is disabled.
- `CANONICAL_SERVICE` is deliberately undeclared in `wrangler.jsonc`:
  without it, canonical memory reads fail closed and task writes stay
  unavailable; the target must independently validate the Firebase bearer.
- Desktop-auth routes mount **before** `/v1/*` authorization on purpose
  (they mint credentials); `exchange` is single-use, 410 on any failure.
- Observability events carry correlation-safe shapes only
  (`test/observability.policy.test.ts`).
- Secrets exist only via `wrangler secret put` (`API_TOKEN`,
  `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`, `FIREBASE_API_KEY`,
  `OPENAI_API_KEY`, `GEMINI_API_KEY`, desktop-token SA trio). Attachment
  routes 503 without the R2 trio; `/v1/*` 401s without `FIREBASE_API_KEY`.

## Commands

From `apps/backend-worker/`:

```sh
bun run dev              # wrangler dev (WRANGLER_SEND_METRICS=false)
bun run test             # bun contract tests + vitest-pool-workers integration tests
bun run typecheck        # tsc --noEmit + wrangler types freshness check
bun run lint             # eslint --max-warnings 0
bun run deploy:dry-run   # strict dry-run deploy
bun run deploy:staging   # real staging deploy (release gate first — see RELEASE.md)
bun run migrate:staging  # D1 migrations apply (remote, evidence-gated)
bun run verify:ready | verify:release | verify:migrations
```

Prefix any hand-written wrangler invocation with
`WRANGLER_SEND_METRICS=false` (and `WRANGLER_WRITE_LOGS=false` for
deploy/migrate). The cron trigger runs every minute (transcription claims);
the 70k-subrequest ceiling requires Workers Paid.

## Testing

`bun run test` runs two layers: Bun tests for contracts/policy (worker,
gateway, live sessions, observability, release gate, migration bytes) and
`@cloudflare/vitest-pool-workers` integration tests against real miniflare
D1/R2/DO with every migration applied (`wrangler.test.jsonc`,
`test/migration-setup.ts`, helpers in `test/d1-mock.ts`). No network or
real credentials needed.

## Gotchas

- Never edit an applied migration — regenerate forward fixes as a new
  migration. 0007/0008 are coordinated client+Worker releases; 0010 is a
  forward-only tenant-scoped PK rebuild; per-migration warnings live in
  RELEASE.md.
- Shared staging bearers cannot use `x-omi-client-id` values beginning with
  `firebase:`; the capture path requires an https `OMI_V5_BACKEND_URL`.
- `worker-configuration.d.ts` is generated; `typecheck` fails when stale —
  rerun `wrangler types` after config changes.
