# Workers-first migration evidence

This note records locally reproducible evidence for the current Omi v5 Workers slices. It is intentionally limited to isolated recovery worktrees and does not claim a deployment or a production migration.

## Authority and boundaries

- **Workers** are the runtime boundary.
- **D1** is authoritative for the migrated tasks read projection (`DB` binding and `0001_tasks.sql`). The focused Cloudflare Vitest integration test proves account-filtered reads from seeded D1 rows.
- **Durable Objects** coordinate per-account state/admission and generation/event sequencing; they are not the authoritative migrated tasks read store.
- **AI traffic**: the gateway slice adds fail-closed configuration, HTTPS-only URL validation, bounded request/response handling, bearer forwarding to the configured Cloudflare AI Gateway/OpenRouter endpoint, and correlation-safe error logs. It does not add a direct provider path or Google backend.
- **Async/runtime operations** remain bounded to the Workers platform surface (R2, Queues, Workflows, and Cron when a slice requires them). No platform or core-foundation worktree is part of this evidence.
- **Observability**: request events are JSON, correlation-safe, and omit URL/query, account identifiers, authorization, request content, prompts, and completions. Wrangler Observability is enabled in the worker configuration; the same privacy-safe line format is suitable for Better Stack ingestion.

## Verified slices

### AI Gateway/OpenRouter adapter

Worktree: `workers-ai-gateway`, commit `2b22fd79a`.

- `bun test apps/backend-worker/test/openrouter.gateway.test.ts`: **10 passed**.
- `bun run --cwd apps/backend-worker typecheck`: **passed**.
- Prettier check on changed TypeScript: **passed**.
- `wrangler deploy --dry-run --config apps/backend-worker/wrangler.jsonc`: **passed**.
- `git diff --check origin/v5...HEAD`: **passed**.

The tests cover request shape, correlation header, response bounds, redaction, malformed upstream responses, and readiness fail-closed behavior.

### D1-authoritative tasks vertical slice

Worktree: `workers-d1-vertical-slice`, commits `d02778936` and `61452d06a`.

- `bun x vitest run test/d1-tasks.integration.test.ts`: **1 passed**.
- `bun run typecheck`: **passed**.
- `wrangler deploy --dry-run --strict`: **passed**, including the D1 binding.
- Prettier and `git diff --check`: **passed** after the ratified tasks contract was formatted in `61452d06a`.

The integration test inserts same-account and foreign-account rows and verifies that the worker returns only the authenticated account's D1 task with the ratified completeness envelope.

### Vectorize vs AI Search permission-filtered benchmark

Worktree: `workers-retrieval-benchmark`, commits `4da4ac0dc` and `d0b09c470`.

- `bun run check`: **25 passed**, with format, lint, typecheck, and tests passing.
- `bun run run`: both in-memory candidate providers passed account-isolation and deletion gates; the intentionally bad provider failed the sensitivity gates.
- Local synthetic metrics: Vectorize p95 latency `13 ms`, p95 index lag `240 ms`; AI Search p95 latency `19 ms`, p95 index lag `90 ms`. Recall/MRR/nDCG were `0.583/0.667/0.602` for both in this fixture.
- `bun run build` followed by Wrangler dry-run: **passed**.

These are local simulations only. No provider winner is selected; hosted comparison requires a deliberate synthetic-only staging run.

### CI, readiness, rollback, and observability

Worktree: `workers-observability`, commits `66853a0ed` and `b2f54fb2f`.

- `bun test test/worker.contract.test.ts test/ready.verify.test.ts`: **54 passed**.
- `bun run typecheck`: **passed**.
- Prettier check: **passed**.
- `bun run deploy:dry-run`: **passed**.

The slice includes guarded staging delivery checks, a no-secret readiness verifier, privacy-safe telemetry tests, and `ROLLBACK.md`. No deploy, push, credential access, or secret value was used for this evidence.

## Remaining gate

This evidence is local and commit-scoped. It is not a deployment approval and does not authorize `deploy:staging`, pushing, or accessing secrets. Before any staged rollout, rerun the scoped gates from the exact candidate commit, verify the configured secret bindings out of band, and follow the rollback document.
