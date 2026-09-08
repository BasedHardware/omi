import type { User } from 'firebase/auth'

// Dev-only fake auth for the perf bench (OMI_BENCH=1). A live Firebase session
// can't survive a repeated bench loop — the project invalidates the refresh token
// after a few refreshes — so we inject a deterministic user instead. This mounts
// the authed shell (AppShellInner + MainViews) every run, exercising the real
// startup/mount path we optimize. It has NO valid token, so api.omi.me calls 401
// (panels render empty); that data is fetched async after app-ready and isn't part
// of the startup cost we measure.
//
// Returns null unless we're actually in a dev bench run, so production auth is
// completely untouched (and `import.meta.env.DEV` lets the fake user tree-shake
// out of packaged renderer bundles).
const BENCH_USER = {
  uid: 'bench-user',
  email: 'bench@local',
  displayName: 'Bench User',
  getIdToken: async () => 'bench-token'
} as unknown as User

export function getBenchUser(): User | null {
  if (!import.meta.env.DEV) return null
  return window.omi?.isBench ? BENCH_USER : null
}
