/** Loopback QA fake — lives outside this repo; routes/auth derived from its source. */
export const QA_API_SERVER_ENTRY =
  '/Users/dazheng/workspace/omi/omi-frontend-unification-and-microapps-project-tracker/prototypes/qa-api-server/server.mjs';

export const LOOPBACK_HOST = '127.0.0.1';
export const QA_BEARER_TOKEN = 'omi-qa-fake-token-v1';
export const GENERATION = 'legacy';

/** Grace period before SIGKILL when stopping the child server. */
export const STOP_GRACE_MS = 5_000;

// §10 launch-gate shakedown, 2026-08-08: touched only to prove `bin/omi-lane`
// + `pnpm install --config.confirmModulesPurge=false` + lanes.mjs L0/L1/L2 run
// end to end from a core-foundation lane worktree before the charter binds.
