// Agent-kernel startup guard. Runs at app boot to validate the production
// SQLite path (the real better-sqlite3 driver, rebuilt for Electron's ABI) that
// unit tests cannot exercise — they inject node:sqlite instead. This is the
// runtime complement to store.test.ts's structural coverage.
//
// Kill-switch philosophy: this is a NON-FATAL guard. If the bundled SQLite
// runtime can't support the AgentStore feature set, or the store can't open its
// database, we log and continue — the app runs, the agent kernel just isn't
// available. It must never crash the app on boot.
//
// PR #3a scope: probe + open/migrate/close only. The AgentRuntimeKernel singleton
// and chat routing are wired in later PRs; nothing consumes the store yet.

import { probeSqliteRuntime, SqliteAgentStore } from './store'

export function probeAgentStoreRuntimeAtStartup(): void {
  try {
    // 1. Fail-fast feature probe on a throwaway :memory: db (STRICT tables,
    //    json_valid CHECKs, partial-unique indexes) using the real driver.
    probeSqliteRuntime()

    // 2. Open the production database on the real driver: exercises migrate()
    //    (all 14 migrations) + reconcileStartup() against the actual on-disk
    //    file. Closed immediately — no consumer holds it in this PR.
    const store = new SqliteAgentStore()
    store.close()

    console.log('[agent-kernel] SQLite runtime probe + store open/migrate succeeded')
  } catch (error) {
    console.error(
      '[agent-kernel] SQLite runtime guard failed — agent kernel will be unavailable this session:',
      error
    )
  }
}
