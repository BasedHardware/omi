# .github — CI notes

One workflow: [`workflows/backend-worker-staging.yml`](workflows/backend-worker-staging.yml).

| Job | Trigger | Runs |
|---|---|---|
| `validate` | push/PR to `main`/`v5`, dispatch | Bun 1.3.14 + JDK 17 setup; `scripts/test-android-http`; workspace build; backend-worker format/lint/typecheck/test; react-native + pwa tests; `platform:check`; example-platform Postgres integration (20-min timeout); backend-worker `deploy:dry-run` |
| `apple-auth` | same | `scripts/test-apple-auth` (macOS runner — do not move to Linux) |
| `deploy` | manual `workflow_dispatch`, `staging` environment | D1 migrations + operator evidence verification (`STAGING_D1_MIGRATION_EVIDENCE_*` vars), worker staging deploy, `verify:release` against `STAGING_WORKER_URL` |

Rules:

- Deploys are manual and evidence-gated on purpose. Do not weaken the
  migration-evidence checks or the `/ready` gate; failures block the deploy
  by design.
- Toolchain pins live here (Bun 1.3.14, Temurin JDK 17). Keep them in sync
  with `package.json` `packageManager` and `scripts/test-android-http`'s
  requirements.
- Staging deploys are Cloudflare-side; there is no production environment in
  this repo.
