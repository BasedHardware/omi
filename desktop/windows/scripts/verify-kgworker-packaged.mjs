#!/usr/bin/env node
// Packaged-load guard for the KG write-worker's native-module chain.
//
// What it proves (the "Cannot find module 'bindings'" regression):
//   kgWorker.js runs in a worker thread loaded from a REAL path
//   (resources/app.asar.unpacked/out/main/kgWorker.js), so its `require()` is plain
//   real-fs anchored at app.asar.unpacked and never crosses into app.asar. If
//   better-sqlite3's pure-JS deps (bindings → file-uri-to-path) are not unpacked,
//   the worker resolves better-sqlite3 but dies the instant it calls
//   require('bindings') — with ZERO build-time signal. This turns that silent
//   runtime crash into a loud build/CI failure.
//
// Steps:
//   1. Produce (or reuse) a packaged --dir build.
//   2. Assert the whole worker native closure is physically present under
//      resources/app.asar.unpacked/node_modules (deterministic; catches a missing glob).
//   3. Spawn the packaged Electron binary as node and, from the UNPACKED worker
//      location, require the packaged better-sqlite3 and open an in-memory Database
//      + run a statement — the exact native chain kgWorker.js executes. Asserts no
//      "Cannot find module" and a clean exit.
//
//   pnpm build:unpack && pnpm verify:kgworker         # explicit two-step
//   pnpm verify:kgworker                              # builds --dir itself
//   OMI_REUSE_BUILD=1 pnpm verify:kgworker            # reuse an existing build

import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { KGWORKER_NATIVE_PACKAGES } from './kgworker-native-closure.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const WIN_ROOT = join(HERE, '..')
const UNPACKED = join(WIN_ROOT, 'dist', 'win-unpacked')

const MODULE_ERR = /ERR_MODULE_NOT_FOUND|Cannot find module|ERR_REQUIRE_ESM|Cannot find package/i

function fail(msg) {
  console.error(`\n[verify-kgworker] FAIL: ${msg}\n`)
  process.exit(1)
}
function step(msg) {
  console.log(`[verify-kgworker] ${msg}`)
}

// --- 1. Build --dir -------------------------------------------------------
if (process.env.OMI_REUSE_BUILD === '1' && existsSync(UNPACKED)) {
  step('reusing existing dist/win-unpacked (OMI_REUSE_BUILD=1)')
} else {
  step('building unpacked app: pnpm build:unpack (this takes a few minutes)…')
  const pnpm = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm'
  const r = spawnSync(pnpm, ['build:unpack'], {
    cwd: WIN_ROOT,
    stdio: 'inherit',
    shell: false
  })
  if (r.status !== 0) fail(`build:unpack exited ${r.status}`)
}
if (!existsSync(UNPACKED)) fail(`no packaged build at ${UNPACKED}`)

const asarUnpackedRoot = join(UNPACKED, 'resources', 'app.asar.unpacked')
if (!existsSync(asarUnpackedRoot)) fail(`no app.asar.unpacked at ${asarUnpackedRoot}`)

// --- locate the packaged Electron binary ----------------------------------
const exes = readdirSync(UNPACKED).filter((f) => f.toLowerCase().endsWith('.exe'))
if (exes.length === 0) fail(`no .exe in ${UNPACKED}`)
const exeName = exes.includes('omi-windows.exe')
  ? 'omi-windows.exe'
  : exes.sort((a, b) => statSync(join(UNPACKED, b)).size - statSync(join(UNPACKED, a)).size)[0]
const exePath = join(UNPACKED, exeName)
step(`packaged binary: ${exeName}`)

// --- 2. Worker native closure present on disk under app.asar.unpacked -----
const missing = KGWORKER_NATIVE_PACKAGES.filter(
  (name) => !existsSync(join(asarUnpackedRoot, 'node_modules', name, 'package.json'))
)
if (missing.length > 0) {
  fail(
    `${missing.length}/${KGWORKER_NATIVE_PACKAGES.length} worker native package(s) NOT unpacked to ` +
      `app.asar.unpacked/node_modules (kgWorker would crash "Cannot find module"): ${missing.join(', ')}. ` +
      `Check KGWORKER_NATIVE_UNPACK_GLOBS in scripts/kgworker-native-closure.mjs is spread into asarUnpack.`
  )
}
step(`closure OK — ${KGWORKER_NATIVE_PACKAGES.join(', ')} all present under app.asar.unpacked`)

// --- 3. Actually load the native chain from the packaged worker location --
// The worker script lives at app.asar.unpacked/out/main/kgWorker.js. Resolving
// 'better-sqlite3' from that directory exercises the same real-fs walk the worker
// does; opening an in-memory Database forces require('bindings') → file-uri-to-path
// → the native .node addon — the exact chain that was crashing. NOTE: :memory: + WAL
// here proves MODULE RESOLUTION + native load (the "Cannot find module" bug); it does
// not exercise the worker's on-disk WAL DB path — that is covered by driving the real
// kgWorker.js against a temp DB (see the PR's live-proof step).
const workerDir = join(asarUnpackedRoot, 'out', 'main')
if (!existsSync(join(workerDir, 'kgWorker.js')))
  fail(`packaged kgWorker.js missing under ${workerDir}`)

const driver = [
  'const dir = process.env.OMI_WORKER_DIR;',
  // Resolve better-sqlite3 exactly as kgWorker.js would from its own directory.
  'const bsqPath = require.resolve("better-sqlite3", { paths: [dir] });',
  'const Database = require(bsqPath);',
  'const db = new Database(":memory:");',
  'db.pragma("journal_mode = WAL");',
  'db.prepare("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)").run();',
  'db.prepare("INSERT INTO t (v) VALUES (?)").run("ok");',
  'const row = db.prepare("SELECT v FROM t WHERE id = 1").get();',
  'db.close();',
  'if (!row || row.v !== "ok") { console.error("BAD_ROW"); process.exit(3); }',
  'console.log("KGWORKER_NATIVE_OK");'
].join('\n')

step('spawn: packaged binary as node → require(better-sqlite3) + in-memory Database…')
const result = await new Promise((resolve) => {
  const child = spawn(exePath, ['-e', driver], {
    cwd: UNPACKED,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',
      NODE_NO_WARNINGS: '1',
      OMI_WORKER_DIR: workerDir
    },
    windowsHide: true
  })
  let out = ''
  child.stdout.on('data', (d) => (out += d.toString()))
  child.stderr.on('data', (d) => (out += d.toString()))
  child.on('error', (err) => resolve({ out, code: null, spawnError: err.message }))
  child.on('exit', (code) => resolve({ out, code }))
})

if (result.spawnError) fail(`could not spawn packaged binary: ${result.spawnError}`)
if (MODULE_ERR.test(result.out)) fail(`worker native chain failed to resolve:\n${result.out}`)
if (result.code !== 0) fail(`native-load driver exited ${result.code}:\n${result.out}`)
if (!/KGWORKER_NATIVE_OK/.test(result.out)) fail(`driver did not report success:\n${result.out}`)

console.log(
  '\n[verify-kgworker] PASS — packaged kgWorker native chain loads (better-sqlite3 + bindings + file-uri-to-path).'
)
console.log(`  binary:  ${exePath}`)
console.log(`  worker:  ${join(workerDir, 'kgWorker.js')}`)
