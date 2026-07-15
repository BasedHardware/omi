#!/usr/bin/env node
// Hermetic, fail-loud drift + completeness guard for pi-mono's asarUnpack closure.
// Runs in postinstall (cheap, no network), so a fresh install or a pi-mono dep
// bump that changes the closure fails automatically — nobody has to remember.
//
// Three guards:
//   1. SANITY (inherited) — computeUnpackGlobs() throws if a pi-mono root doesn't
//      resolve or the closure collapsed below the floor (partial/broken install).
//   2. DRIFT — compute the closure FRESH in memory, then diff it against the
//      COMMITTED scripts/pimono-asar-unpack.generated.json. If they differ, someone
//      changed pi-mono's dependency tree without regenerating + committing the list.
//      Fail loud with the exact added/removed globs. (This is only meaningful
//      because the file is COMMITTED and we do NOT regenerate it first — the whole
//      point of the guard.)
//   3. COMPLETENESS — every glob in the committed list resolves on disk, so a
//      closure package can't be missing at pack time → ERR_MODULE_NOT_FOUND when the
//      packaged pi child require()s it.
//
//   pnpm verify:pimono-unpack

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { computeUnpackGlobs, GENERATED_FILE, WIN_ROOT } from './gen-pimono-unpack.mjs'

function fail(lines) {
  console.error('\n[verify-pimono-unpack] FAILED:\n')
  for (const l of [].concat(lines)) console.error(`  - ${l}\n`)
  process.exit(1)
}

// --- Guard 1: sanity (fresh walk; throws on unresolved root / collapsed closure) ---
let fresh, closureSize, coveredCount
try {
  ;({ globs: fresh, closureSize, coveredCount } = computeUnpackGlobs())
} catch (err) {
  fail(err instanceof Error ? err.message : String(err))
}

// --- Guard 2: drift (fresh in-memory vs the COMMITTED file — do NOT regenerate) ---
if (!existsSync(GENERATED_FILE)) {
  fail(
    `committed closure list is missing: ${GENERATED_FILE}\n` +
      `      Run: pnpm gen:pimono-unpack, then commit scripts/pimono-asar-unpack.generated.json`
  )
}
let committed
try {
  committed = JSON.parse(readFileSync(GENERATED_FILE, 'utf8'))
} catch (err) {
  fail(`committed closure list is not valid JSON: ${err instanceof Error ? err.message : err}`)
}
if (!Array.isArray(committed)) {
  fail(`committed closure list is not a JSON array: ${GENERATED_FILE}`)
}

const freshSet = new Set(fresh)
const committedSet = new Set(committed)
const added = fresh.filter((g) => !committedSet.has(g)) // in tree, missing from file
const removed = committed.filter((g) => !freshSet.has(g)) // in file, gone from tree
if (added.length > 0 || removed.length > 0) {
  const lines = [
    'pi-mono closure DRIFT — the committed list is out of date vs a fresh dependency walk.',
    'Run: pnpm gen:pimono-unpack, then commit scripts/pimono-asar-unpack.generated.json'
  ]
  if (added.length > 0)
    lines.push(`Missing from committed file (${added.length}): ${added.join(', ')}`)
  if (removed.length > 0)
    lines.push(`Stale in committed file (${removed.length}): ${removed.join(', ')}`)
  fail(lines)
}

// --- Guard 3: completeness (every committed glob resolves on disk) ---
const missingOnDisk = []
for (const glob of committed) {
  const rel = glob.replace(/\/\*\*$/, '') // node_modules/<name>
  if (!existsSync(join(WIN_ROOT, rel, 'package.json'))) missingOnDisk.push(rel)
}
if (missingOnDisk.length > 0) {
  fail(
    `${missingOnDisk.length} closure package(s) in the committed list do not resolve on disk ` +
      `(would ERR_MODULE_NOT_FOUND when packaged pi spawns):\n      ${missingOnDisk.join('\n      ')}\n` +
      `      Run: pnpm install (from desktop/windows/).`
  )
}

console.log(
  `[verify-pimono-unpack] OK — ${fresh.length} unpack globs, ${closureSize} packages in closure ` +
    `(${coveredCount} already covered), committed list fresh + all present on disk.`
)
