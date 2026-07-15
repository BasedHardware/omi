#!/usr/bin/env node
// Fail-loud staleness + completeness check for pi-mono's asarUnpack closure.
//
// Two guards, both hermetic (read node_modules only — safe for postinstall/CI):
//   1. STALENESS — re-walk pi's dependency graph and diff against the committed
//      generated file (build/pimono-asar-unpack.generated.json). If they differ,
//      the generated artifact is out of date (a pi-mono version bump added/removed
//      a transitive dep, or someone hand-edited the file). Fail loud so a stale
//      list can't silently ship. NOTE: electron-builder.config.mjs recomputes the
//      closure fresh at pack time, so the BUILD itself can't ship a stale list —
//      this guard keeps the inspectable artifact honest and catches drift early.
//   2. COMPLETENESS — assert every package in the freshly-walked closure actually
//      resolves in node_modules. A closure package missing from the install →
//      ERR_MODULE_NOT_FOUND when the packaged pi child spawns, with no other
//      build-time signal (the same blind spot check-agent-deps.mjs guards for the
//      direct deps, extended here to the whole transitive closure).
//
//   pnpm verify:pimono-unpack

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { computeUnpackGlobs, GENERATED_FILE, WIN_ROOT } from './gen-pimono-unpack.mjs'

const errors = []

const { globs: fresh, closureSize, coveredCount } = computeUnpackGlobs()

// --- Guard 1: staleness ---------------------------------------------------
if (!existsSync(GENERATED_FILE)) {
  errors.push(`generated file is missing: ${GENERATED_FILE}\n      Run: pnpm gen:pimono-unpack`)
} else {
  let committed
  try {
    committed = JSON.parse(readFileSync(GENERATED_FILE, 'utf8'))
  } catch (err) {
    committed = null
    errors.push(`generated file is not valid JSON: ${err instanceof Error ? err.message : err}`)
  }
  if (Array.isArray(committed)) {
    const freshSet = new Set(fresh)
    const committedSet = new Set(committed)
    const added = fresh.filter((g) => !committedSet.has(g))
    const removed = committed.filter((g) => !freshSet.has(g))
    if (added.length > 0 || removed.length > 0) {
      const lines = [
        'generated asarUnpack list is STALE vs a fresh dependency-graph walk.',
        '      Run: pnpm gen:pimono-unpack, then commit the result.'
      ]
      if (added.length > 0)
        lines.push(`      Missing from file (${added.length}): ${added.join(', ')}`)
      if (removed.length > 0)
        lines.push(`      Stale in file (${removed.length}): ${removed.join(', ')}`)
      errors.push(lines.join('\n'))
    }
  }
}

// --- Guard 2: completeness ------------------------------------------------
const missingOnDisk = []
for (const glob of fresh) {
  // glob is `node_modules/<pkg>/**` — strip the trailing /** and check the dir.
  const rel = glob.replace(/\/\*\*$/, '')
  if (!existsSync(join(WIN_ROOT, rel, 'package.json'))) {
    missingOnDisk.push(rel)
  }
}
if (missingOnDisk.length > 0) {
  errors.push(
    `${missingOnDisk.length} closure package(s) in the walk do not resolve on disk ` +
      `(would ERR_MODULE_NOT_FOUND when packaged pi spawns):\n      ${missingOnDisk.join('\n      ')}\n` +
      '      Run: pnpm install (from desktop/windows/).'
  )
}

if (errors.length > 0) {
  console.error('\n[verify-pimono-unpack] FAILED:\n')
  for (const e of errors) console.error(`  - ${e}\n`)
  process.exit(1)
}

console.log(
  `[verify-pimono-unpack] OK — ${fresh.length} unpack globs, ${closureSize} packages in closure ` +
    `(${coveredCount} already covered), all present on disk, generated file fresh.`
)
