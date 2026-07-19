// Post-build guard for the main+preload V8 bytecode compilation
// (electron.vite.config.ts → build.bytecode). Runs after `electron-vite build`
// in the `build` npm script.
//
// WHY: electron-vite's bytecode plugin is SILENT when it can't run — if the main
// or preload output ever becomes ESM (e.g. someone adds "type":"module" to
// package.json or forces output.format:'es'), the plugin logs a yellow warning
// and emits plain JS with NO error. The perf win would vanish unnoticed and the
// shipped installer would quietly lose it. This check turns that silent no-op
// into a loud build failure. It also guards the OTHER direction: kgWorker (a
// worker-thread entry loaded via new Worker()) must STAY plain JS — if it ever
// gets bytecoded it would fail to load at runtime in the worker thread.
//
// Matches AGENTS.md "back rules with checks — enforced rules don't drift".
import { existsSync, statSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const p = (rel) => path.join(root, rel)

const errors = []

// 1. The bytecoded entries must exist and be non-trivial. Their presence is the
//    proof that build.bytecode actually ran (CJS output + production mode).
for (const rel of ['out/main/index.jsc', 'out/preload/index.jsc']) {
  const abs = p(rel)
  if (!existsSync(abs)) {
    errors.push(
      `${rel} is MISSING — bytecode did not run. The main/preload output is likely no ` +
        `longer CJS (electron-vite bytecode is CJS-only and fails silently on ESM). ` +
        `Check package.json "type" and electron.vite.config.ts output.format.`
    )
  } else if (statSync(abs).size < 1024) {
    errors.push(`${rel} exists but is suspiciously small (${statSync(abs).size} bytes).`)
  }
}

// 2. The entry .js files must be the tiny bootstrap stub (require loader + .jsc),
//    confirming the entry is actually served from bytecode.
for (const rel of ['out/main/index.js', 'out/preload/index.js']) {
  const abs = p(rel)
  if (existsSync(abs)) {
    const code = readFileSync(abs, 'utf8')
    if (!code.includes('bytecode-loader.cjs') || !code.includes('.jsc')) {
      errors.push(`${rel} is not the bytecode bootstrap stub — bytecode may not be active.`)
    }
  }
}

// 3. kgWorker MUST stay plain JS. It is loaded via new Worker(kgWorker.js) in a
//    worker thread that has no bytecode loader registered, so a bytecoded worker
//    entry (a stub requiring kgWorker.jsc) would fail to load.
const kg = p('out/main/kgWorker.js')
if (existsSync(kg)) {
  const code = readFileSync(kg, 'utf8')
  if (code.includes('.jsc') || existsSync(p('out/main/kgWorker.jsc'))) {
    errors.push(
      'out/main/kgWorker.js appears bytecoded — it MUST stay plain JS (it runs in a ' +
        'worker thread with no bytecode loader). Do not add "kgWorker" to bytecode.chunkAlias.'
    )
  }
} else {
  errors.push('out/main/kgWorker.js is missing — expected the KG write-worker entry.')
}

if (errors.length) {
  console.error('\n[verify-bytecode] FAILED:')
  for (const e of errors) console.error('  - ' + e)
  process.exit(1)
}
console.log('[verify-bytecode] OK — main+preload bytecode present, kgWorker plain.')
