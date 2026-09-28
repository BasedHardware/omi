# .github — CI notes

Staging deploy paused after the move into `main`; relocating it needs its own PR through `main`'s deployment-secret-boundary and deploy-concurrency policies.

The nested [`workflows/backend-worker-staging.yml`](workflows/backend-worker-staging.yml)
is inert. Root `.github/workflows/v5-checks.yml` runs checks.

| Historical nested job (inert) | Former trigger | Runs |
|---|---|---|
| `validate` | push/PR to `main`/`v5`, dispatch | Bun 1.3.14 + JDK 17 setup; `v5/scripts/test-android-http`; workspace build; backend-worker format/lint/typecheck/test; react-native + pwa tests; `platform:check`; example-platform Postgres integration (20-min timeout); backend-worker `deploy:dry-run` |
| `apple-auth` | same | `v5/scripts/test-apple-auth` (macOS runner — do not move to Linux) |
| `deploy` | manual `workflow_dispatch`, `staging` environment | D1 migrations + operator evidence verification (`STAGING_D1_MIGRATION_EVIDENCE_*` vars), worker staging deploy, `verify:release` against `STAGING_WORKER_URL` |

Rules:

- The nested deploy was manual and evidence-gated. Keep the migration-evidence
  checks and `/ready` gate intact until a separately reviewed relocation.
- Toolchain pins live here (Bun 1.3.14, Temurin JDK 17). Keep them in sync
  with `package.json` `packageManager` and `v5/scripts/test-android-http`'s
  requirements.
- Staging deploys are Cloudflare-side; there is no production environment in
  this repo.
