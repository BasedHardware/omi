#!/usr/bin/env node
// Fails LOUD, at install/build time, when a runtime dependency the coding-agent
// (ACP) system needs is missing from node_modules.
//
// The failure mode this guards against: `@agentclientprotocol/claude-agent-acp`
// was present in pnpm-lock.yaml but absent from node_modules on a fresh
// checkout. Nothing caught it at build time because it is loaded two different
// ways that a bundler never resolution-checks:
//   - src/main/codingAgent/claude-acp-entry.mjs pulls it in via a dynamic
//     `await import(...)` (deliberately, so its module-load console noise never
//     hits stdout before the console redirect — see that file's header comment).
//   - src/main/codingAgent/claudeCode.ts imports its own entry script via a
//     `?asset` import, which electron-vite treats as an opaque path string, not
//     a module to bundle.
// Every agent task failed ERR_MODULE_NOT_FOUND at runtime with zero build-time
// signal. `better-sqlite3` and `koffi` are native addons that electron-vite
// externalizes rather than bundles, so they have the same blind spot.
//
// Run automatically via `postinstall`; also runnable standalone:
//   pnpm check:agent-deps

import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const CRITICAL_DEPS = [
  '@agentclientprotocol/claude-agent-acp', // dynamically imported by src/main/codingAgent/claude-acp-entry.mjs
  // The pi CLI (spawned by src/main/codingAgent/piMono.ts under
  // ELECTRON_RUN_AS_NODE) and its runtime peer. Resolved by createRequire at
  // runtime, so a bundler never resolution-checks them — same ERR_MODULE_NOT_FOUND
  // blind spot as the ACP entry.
  '@earendil-works/pi-coding-agent',
  '@earendil-works/pi-ai',
  'better-sqlite3', // native addon — src/main/ipc/db.ts, kgWorker.ts, integrations/stickyNotes.ts
  'koffi' // native addon — src/main/bar/keyState.ts, meeting/processSnapshot.ts, meeting/micConsentStore.ts, usage/*
]

const missing = []
for (const dep of CRITICAL_DEPS) {
  try {
    import.meta.resolve(dep)
  } catch (err) {
    missing.push({ dep, message: err instanceof Error ? err.message : String(err) })
  }
}

// pi-mono spawns the CLI file directly (bin.pi = dist/cli.js). The package's
// exports map does not expose that subpath, so piMono.ts resolves the package
// root and derives the sibling cli.js — mirror that here so a missing/renamed
// cli.js fails loud at install/build, not at first agent turn.
try {
  const indexPath = fileURLToPath(import.meta.resolve('@earendil-works/pi-coding-agent'))
  const cliPath = join(dirname(indexPath), 'cli.js')
  if (!existsSync(cliPath)) {
    missing.push({
      dep: '@earendil-works/pi-coding-agent/dist/cli.js',
      message: `resolved package root but cli.js is absent at ${cliPath}`
    })
  }
} catch (err) {
  // A failure here is already reported by the '@earendil-works/pi-coding-agent'
  // entry above; only add detail if that somehow resolved.
  if (!missing.some((m) => m.dep === '@earendil-works/pi-coding-agent')) {
    missing.push({
      dep: '@earendil-works/pi-coding-agent/dist/cli.js',
      message: err instanceof Error ? err.message : String(err)
    })
  }
}

if (missing.length > 0) {
  console.error(
    '\n[check-agent-deps] Missing runtime dependencies — the app WILL crash at runtime ' +
      '(ERR_MODULE_NOT_FOUND) with no build-time warning otherwise:\n'
  )
  for (const { dep, message } of missing) {
    console.error(`  - ${dep}\n      ${message}`)
  }
  console.error(
    '\nFix: run `pnpm install` from desktop/windows/. If the problem persists, delete ' +
      'node_modules and reinstall.\n'
  )
  process.exit(1)
}

console.log(`[check-agent-deps] OK — resolved: ${CRITICAL_DEPS.join(', ')}`)
