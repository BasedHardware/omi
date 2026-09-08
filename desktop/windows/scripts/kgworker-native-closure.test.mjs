// Hermetic guard for the KG write-worker's native-module asarUnpack closure.
//
// Regression: kgWorker.js runs from a REAL path (app.asar.unpacked/out/main/) so
// its require() is plain real-fs and never crosses into app.asar. better-sqlite3
// is auto-unpacked (native .node) but its pure-JS deps (bindings → file-uri-to-path)
// were left inside app.asar → the worker died "Cannot find module 'bindings'".
//
// This fast, hermetic test asserts the fix stays wired AND stays correct as
// better-sqlite3 evolves: the electron-builder config must spread every worker-native
// unpack glob into asarUnpack, every declared package must resolve on disk, and the
// pinned closure must still equal better-sqlite3's ACTUAL declared runtime dependency
// graph (so a future bump that swaps the native loader — e.g. bindings →
// node-gyp-build — goes RED here instead of crashing the packaged worker with no
// signal). The full packaged proof that the chain LOADS lives in
// scripts/verify-kgworker-packaged.mjs (heavy; run on a real build).
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, realpathSync } from 'node:fs'
import { basename, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import builderConfig from '../electron-builder.config.mjs'
import {
  KGWORKER_NATIVE_PACKAGES,
  KGWORKER_NATIVE_UNPACK_GLOBS
} from './kgworker-native-closure.mjs'

const WIN_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

// The root the worker require()s; the rest of the closure is whatever it pulls in.
const ROOT = 'better-sqlite3'

// Deps that appear in a package.json but are NEVER require()d at runtime by the
// worker's code path, so they must NOT be unpacked. prebuild-install is
// better-sqlite3's install-time tool (downloads the prebuilt .node); it and its
// large tree are dead weight at runtime. Keep this list tiny and justified.
const INSTALL_TIME_ONLY = new Set(['prebuild-install'])

// Resolve a package dir by walking node_modules up from `fromDir` (Node's
// algorithm). The CI install can retain a transitive dependency below its
// consumer even though the packaged app later re-flattens it at the root.
function resolvePkgDir(name, fromDir) {
  let dir = fromDir
  for (;;) {
    // At a node_modules directory, Node goes to its parent before adding the
    // next lookup candidate; it never probes node_modules/node_modules.
    if (basename(dir) !== 'node_modules') {
      const candidate = join(dir, 'node_modules', name)
      if (existsSync(join(candidate, 'package.json'))) return realpathSync(candidate)
    }
    const parent = dirname(dir)
    if (parent === dir) return null
    dir = parent
  }
}

// Walk ROOT's DECLARED runtime dependency graph (dependencies, transitively),
// skipping the install-time denylist. This is the set that must live on disk for
// the worker; it may safely over-approximate the exact require() closure (extra
// unpacked files are harmless) but must never under-approximate.
function walkDeclaredRuntimeClosure() {
  const locations = new Map()
  const queue = [{ name: ROOT, fromDir: WIN_ROOT }]
  while (queue.length) {
    const { name, fromDir } = queue.shift()
    if (locations.has(name) || INSTALL_TIME_ONLY.has(name)) continue
    const dir = resolvePkgDir(name, fromDir)
    locations.set(name, dir)
    if (!dir) continue // unresolved names still surface in `locations` → equality fails loud
    const pkg = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'))
    for (const dep of Object.keys(pkg.dependencies ?? {})) {
      queue.push({ name: dep, fromDir: dir })
    }
  }
  return locations
}

describe('kgWorker native-module closure', () => {
  it('spreads every worker-native glob into electron-builder asarUnpack', () => {
    const unpack = builderConfig.asarUnpack ?? []
    for (const glob of KGWORKER_NATIVE_UNPACK_GLOBS) {
      expect(unpack, `asarUnpack is missing ${glob} — packaged kgWorker would crash`).toContain(
        glob
      )
    }
  })

  it('every declared closure package resolves from its runtime consumer', () => {
    const locations = walkDeclaredRuntimeClosure()
    for (const name of KGWORKER_NATIVE_PACKAGES) {
      expect(
        locations.get(name),
        `${name} not installed — the closure references a package that no longer exists`
      ).toBeTruthy()
    }
  })

  it('pinned closure equals better-sqlite3’s actual declared runtime dep graph', () => {
    // If better-sqlite3 (or a dep) changes its runtime dependencies — e.g. swaps
    // bindings for node-gyp-build, or bindings adds a new pure-JS dep — the walked
    // set diverges from the pinned list and this goes RED. Re-derive
    // KGWORKER_NATIVE_PACKAGES (and re-run pnpm verify:kgworker) when it does.
    const walked = [...walkDeclaredRuntimeClosure().keys()].sort()
    expect(
      walked,
      'better-sqlite3’s declared runtime deps changed — re-derive KGWORKER_NATIVE_PACKAGES ' +
        'in scripts/kgworker-native-closure.mjs and re-run pnpm verify:kgworker'
    ).toEqual([...KGWORKER_NATIVE_PACKAGES].sort())
  })
})
