// Full-shell module-eval smoke. Guards the "blank renderer" class: any throw
// while evaluating the real App module graph (circular-import TDZ error,
// rejected top-level await, module-scope throw such as a service init like
// Firebase) aborts the whole renderer bundle and the window renders BLACK with
// no UI error surface. Component-level tests never catch this because they
// import leaf modules, not the shell. This test evaluates the exact graph
// main.tsx bootstraps (App + its static imports, which include every page via
// MainViews), so it goes red on any module-eval regression.
//
// Scope note (verified empirically): importing a NON-EXISTENT NAMED EXPORT is
// a browser-ESM SyntaxError that also blanks the renderer, but Vitest's SSR
// transform degrades it to `undefined`, so THIS test cannot see it. That class
// is caught by `npm run typecheck:web` (tsc errors on missing exports). The
// blank-renderer gate is therefore typecheck + this smoke together.
//
// 2026-07-02 incident: the app booted to a fully black window. Root cause was
// an uncaught module-scope FirebaseError (auth/invalid-api-key) from
// lib/firebase.ts when .env was absent (VITE_FIREBASE_API_KEY undefined).
// This exact failure reproduces here when the env fallback below is removed
// and no .env exists (red-proven during the incident fix).
import { describe, expect, it, vi } from 'vitest'

// Fallback Firebase env so the shell graph is evaluable on machines/CI without
// a local .env (the app itself still needs a real .env; see .env.example).
// Values are only presence-checked at init; no network call happens in tests.
// Real .env values, when present, take precedence and are left untouched.
if (!import.meta.env.VITE_FIREBASE_API_KEY) {
  vi.stubEnv('VITE_FIREBASE_API_KEY', 'test-shell-smoke-api-key')
  vi.stubEnv('VITE_FIREBASE_AUTH_DOMAIN', 'test.firebaseapp.com')
  vi.stubEnv('VITE_FIREBASE_PROJECT_ID', 'test-project')
}

// Minimal stand-ins for browser globals the renderer genuinely has at runtime
// (this suite runs in the node environment; jsdom is not a dependency of this
// repo). Only add globals the real renderer provides -- never stub the preload
// bridge objects themselves beyond existence, so accidental module-scope CALLS
// into preload APIs still surface as failures.
function memoryStorage(): Storage {
  const map = new Map<string, string>()
  return {
    get length() {
      return map.size
    },
    clear: () => map.clear(),
    getItem: (k: string) => map.get(k) ?? null,
    key: (i: number) => [...map.keys()][i] ?? null,
    removeItem: (k: string) => void map.delete(k),
    setItem: (k: string, v: string) => void map.set(k, String(v))
  }
}
vi.stubGlobal('localStorage', memoryStorage())
vi.stubGlobal('sessionStorage', memoryStorage())

describe('renderer shell', () => {
  it('evaluates the full App module graph without throwing', async () => {
    // Dynamic import so the env fallback above is applied first.
    const mod = await import('./App')
    expect(typeof mod.default).toBe('function')
  })
})
