#!/usr/bin/env node
// Packaged-spawn smoke for pi-mono — the FIRST proof that pi actually launches
// from a packaged (asar) build, not just from the dev tree.
//
// What it proves (the M2 risk):
//   - piMono.ts spawns pi as a plain-Node child (ELECTRON_RUN_AS_NODE) and
//     resolves cli.js via import.meta.resolve. That was only ever exercised in
//     raw node / dev. A packaged build hides two failure modes with ZERO
//     build-time signal: (a) a transitive dep missing from the asarUnpack closure
//     → ERR_MODULE_NOT_FOUND at pi startup; (b) the omi-provider extension .ts not
//     copied next to the packaged main bundle → the extension never loads.
//
// Steps:
//   1. Produce a packaged --dir build (electron-builder --dir; no installer/
//      signing — fast). Skipped if OMI_REUSE_BUILD=1 and dist/win-unpacked exists.
//   2. Assert pi's WHOLE runtime closure is physically present under
//      resources/app.asar.unpacked (deterministic; catches a missing glob).
//   3. Spawn the packaged Electron binary as node against the packaged cli.js in
//      --mode rpc with the packaged extension (mirrors piMono.ts start()), and
//      assert it launches with NO ERR_MODULE_NOT_FOUND / "Cannot find module" and
//      that the extension actually loaded (its `[omi-tools]` startup line).
//   4. Also spawn `cli.js --version` to prove pi's own module graph loads through
//      the packaged Electron-as-node.
//
//   pnpm build:unpack && pnpm verify:pimono-spawn      # explicit two-step
//   pnpm verify:pimono-spawn                           # builds --dir itself
//   OMI_REUSE_BUILD=1 pnpm verify:pimono-spawn         # reuse an existing build

import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { computeUnpackGlobs } from './gen-pimono-unpack.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const WIN_ROOT = join(HERE, '..')
const UNPACKED = join(WIN_ROOT, 'dist', 'win-unpacked')

const MODULE_ERR = /ERR_MODULE_NOT_FOUND|Cannot find module|ERR_REQUIRE_ESM|Cannot find package/i

function fail(msg) {
  console.error(`\n[verify-pimono-spawn] FAIL: ${msg}\n`)
  process.exit(1)
}
function step(msg) {
  console.log(`[verify-pimono-spawn] ${msg}`)
}

// --- 1. Build --dir -------------------------------------------------------
if (process.env.OMI_REUSE_BUILD === '1' && existsSync(UNPACKED)) {
  step('reusing existing dist/win-unpacked (OMI_REUSE_BUILD=1)')
} else {
  step('building unpacked app: npm run build:unpack (this takes a few minutes)…')
  const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm'
  const r = spawnSync(npm, ['run', 'build:unpack'], {
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

// --- 2. Closure present on disk under app.asar.unpacked -------------------
const { globs } = computeUnpackGlobs()
const missing = []
for (const glob of globs) {
  // glob is `node_modules/<pkg>/**` with forward slashes; join() splits the
  // segments onto the platform separator.
  const segments = glob.replace(/\/\*\*$/, '').split('/')
  if (!existsSync(join(asarUnpackedRoot, ...segments, 'package.json'))) missing.push(glob)
}
if (missing.length > 0) {
  fail(
    `${missing.length}/${globs.length} closure package(s) NOT unpacked to app.asar.unpacked ` +
      `(would ERR_MODULE_NOT_FOUND at runtime):\n      ${missing.slice(0, 25).join('\n      ')}` +
      (missing.length > 25 ? `\n      …and ${missing.length - 25} more` : '')
  )
}
step(`closure OK — all ${globs.length} unpack globs present under app.asar.unpacked`)

// --- resolve the packaged cli.js + extension ------------------------------
const cliJs = join(
  asarUnpackedRoot,
  'node_modules',
  '@earendil-works',
  'pi-coding-agent',
  'dist',
  'cli.js'
)
const extension = join(asarUnpackedRoot, 'out', 'main', 'pi-mono-extension', 'index.ts')
if (!existsSync(cliJs)) fail(`packaged cli.js missing: ${cliJs}`)
if (!existsSync(extension)) fail(`packaged extension missing: ${extension}`)
step('packaged cli.js and pi-mono-extension/index.ts both present')

// helper: spawn the packaged binary as node with pi args, collect output.
function runPi(args, { timeoutMs, expectAlive }) {
  return new Promise((resolve) => {
    const child = spawn(exePath, args, {
      cwd: UNPACKED,
      env: {
        ...process.env,
        ELECTRON_RUN_AS_NODE: '1',
        NODE_NO_WARNINGS: '1',
        OMI_API_KEY: 'dummy-smoke-token'
      },
      windowsHide: true
    })
    let out = ''
    child.stdout.on('data', (d) => (out += d.toString()))
    child.stderr.on('data', (d) => (out += d.toString()))
    let timer = null
    let killed = false
    child.on('error', (err) => resolve({ out, code: null, spawnError: err.message }))
    child.on('exit', (code) => {
      if (timer) clearTimeout(timer)
      resolve({ out, code, killed })
    })
    if (expectAlive) {
      timer = setTimeout(() => {
        killed = true
        child.kill('SIGTERM')
      }, timeoutMs)
    }
  })
}

// --- 4. `cli.js --version` — pi's own module graph loads via packaged node ---
step('spawn: cli.js --version (closure load through packaged Electron-as-node)…')
const ver = await runPi([cliJs, '--version'], { timeoutMs: 20000, expectAlive: false })
if (ver.spawnError) fail(`could not spawn packaged binary: ${ver.spawnError}`)
if (MODULE_ERR.test(ver.out)) fail(`module resolution error on --version:\n${ver.out}`)
if (ver.code !== 0)
  fail(`cli.js --version exited ${ver.code} (no module error, but non-zero):\n${ver.out}`)
step(`  --version OK → ${ver.out.trim().split('\n').pop()}`)

// --- 3. rpc + extension — mirrors piMono.ts start() -----------------------
step('spawn: cli.js --mode rpc -e <extension> --provider omi (mirrors start())…')
const rpc = await runPi(
  [cliJs, '--mode', 'rpc', '-e', extension, '--provider', 'omi', '--model', 'omi-sonnet'],
  { timeoutMs: 10000, expectAlive: true }
)
if (rpc.spawnError) fail(`could not spawn rpc: ${rpc.spawnError}`)
if (MODULE_ERR.test(rpc.out)) fail(`module resolution error in rpc startup:\n${rpc.out}`)
if (rpc.code !== null && rpc.code !== 0 && !rpc.killed) {
  fail(`rpc process exited ${rpc.code} before the timeout (unexpected crash):\n${rpc.out}`)
}
// The extension emits `[omi-tools] …` from its bridge client on load — proof the
// packaged .ts extension was found and loaded by jiti from the asarUnpacked tree.
if (!/\[omi-tools\]/.test(rpc.out)) {
  fail(
    `extension did not load — no [omi-tools] startup line (extension packaging broken):\n${rpc.out}`
  )
}
step('  rpc + extension OK — no module errors, extension loaded, daemon stayed alive')

console.log('\n[verify-pimono-spawn] PASS — packaged pi-mono spawns cleanly from the asar build.')
console.log(`  binary:    ${exePath}`)
console.log(`  cli.js:    ${cliJs}`)
console.log(`  extension: ${extension}`)
console.log(`  closure:   ${globs.length} packages unpacked to app.asar.unpacked`)
