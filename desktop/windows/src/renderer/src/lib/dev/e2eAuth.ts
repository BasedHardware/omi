import type { User } from 'firebase/auth'

// Offline fake auth for E2E, gated on the runtime flag OMI_E2E_FAKE_AUTH=1
// (surfaced via the preload as window.omi.e2eFakeAuth). Unlike the perf-bench
// seam (benchAuth, DEV-gated so it tree-shakes out of packaged bundles), this
// one must survive the PRODUCTION renderer build — the shell E2E launches the
// real `electron-vite build` output (out/), where import.meta.env.DEV is false,
// so a DEV gate would make the authed shell unreachable in that harness.
//
// Safety: this returns null unless the process was started with
// OMI_E2E_FAKE_AUTH=1 (a dedicated flag the app never sets itself), so it can
// NEVER activate in normal use. The fake user carries no valid token — every
// api.omi.me call 401s and panels render empty — but the sidebar/shell layout
// (the thing under test) renders synchronously from this object, so geometry
// assertions and screenshots are deterministic and fully offline.
const E2E_USER = {
  uid: 'e2e-user',
  email: 'e2e@local',
  displayName: 'E2E User',
  photoURL: null,
  getIdToken: async () => 'e2e-token'
} as unknown as User

export function getE2EUser(): User | null {
  return window.omi?.e2eFakeAuth ? E2E_USER : null
}
