import { describe, it, expect } from 'vitest'

// Regression guard for the CI break where two capture suites died on IMPORT with
// `auth/invalid-api-key`.
//
// `lib/firebase.ts` constructs `auth` at module scope, and the Firebase SDK
// validates the API key right there — so importing this module (or anything that
// transitively imports it) requires a key to EXIST. Developers have a real .env,
// so every local run passed; CI has none, so the key was undefined and the import
// threw before a single test executed. That is why this was invisible until it
// hit CI.
//
// vitest.config.ts now supplies placeholder VITE_FIREBASE_* values when no .env
// is present. If that config is ever removed, this test fails immediately and
// names the cause — instead of two unrelated capture suites failing in CI only.
describe('lib/firebase is importable without real credentials', () => {
  it('exposes auth after import', async () => {
    const mod = await import('./firebase')
    expect(mod.auth).toBeDefined()
  })

  it('has a Firebase API key in the test env', () => {
    // The specific failure mode: an EMPTY/undefined key. Any non-empty value
    // keeps the SDK constructible offline (it only rejects at request time).
    expect(import.meta.env.VITE_FIREBASE_API_KEY).toBeTruthy()
  })
})
