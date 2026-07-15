#!/usr/bin/env node
// Generates the asarUnpack glob list for pi-mono's full runtime closure.
//
// Why this exists: pi-mono (@earendil-works/pi-coding-agent) is spawned as a
// plain-Node child (ELECTRON_RUN_AS_NODE) by src/main/codingAgent/piMono.ts, so
// EVERY package it require()s at runtime must live OUTSIDE the asar archive — a
// plain-Node child cannot read scripts from asar. pi's closure is ~128 packages
// (AWS SDK, google-auth-library, protobufjs, openai, @mistralai/mistralai,
// @google/genai, jiti, undici, the native @mariozechner/clipboard-* addon, the
// @silvia-odwyer/photon-node WASM, …). Hand-listing that many globs in YAML
// silently drifts on a pi-mono version bump: a new transitive dep upstream →
// ERR_MODULE_NOT_FOUND in production with ZERO build-time signal.
//
// This module walks pi's dependency graph (dependencies + optionalDependencies,
// transitively) over the installed node_modules tree and emits the resolvable
// package set as `node_modules/<pkg>/**` globs. optionalDependencies MUST be
// included: native per-platform addons (e.g. @mariozechner/clipboard-win32-x64-msvc)
// ship as optional deps. Packages already covered by a broader existing
// asarUnpack glob (koffi, the ACP closure) are skipped to avoid duplicates.
//
// `computeUnpackGlobs()` is pure (no side effects) so electron-builder.config.mjs
// and verify-pimono-unpack.mjs can both consume it. The CLI writes
// build/pimono-asar-unpack.generated.json (gitignored; regenerated at
// install/build time) for inspection and as the artifact the staleness check
// diffs against.
//
//   node scripts/gen-pimono-unpack.mjs           # write the generated file
//   node scripts/gen-pimono-unpack.mjs --print   # print globs to stdout, no write

import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
export const WIN_ROOT = resolve(HERE, '..')
export const GENERATED_FILE = join(WIN_ROOT, 'build', 'pimono-asar-unpack.generated.json')

// Roots of pi-mono's runtime closure — the two packages piMono.ts spawns/loads.
const ROOTS = ['@earendil-works/pi-coding-agent', '@earendil-works/pi-ai']

// Package names already covered by a broader glob in electron-builder.config.mjs's
// static asarUnpack list — don't emit duplicate globs for these. Any package
// UNDER these scopes/names is already on disk.
const ALREADY_COVERED_PREFIXES = [
  '@earendil-works/', // node_modules/@earendil-works/**
  '@agentclientprotocol/', // ACP closure
  '@anthropic-ai/claude-agent-sdk', // ACP sdk + platform binaries
  'koffi', // native addon
  'zod' // ACP closure resolves it hoisted
]

function isAlreadyCovered(name) {
  return ALREADY_COVERED_PREFIXES.some((p) => name === p || name.startsWith(p))
}

// Resolve a package's on-disk directory by walking node_modules up from `fromDir`
// (node's own algorithm). Returns the real (symlink-collapsed) directory, or null
// if the package is not installed (an optionalDependency for another platform, or
// a dep pnpm pruned). Under node-linker=hoisted the top-level node_modules is
// flat, but nested copies (version conflicts) still resolve correctly this way.
function resolvePackageDir(name, fromDir) {
  let dir = fromDir
  for (;;) {
    const candidate = join(dir, 'node_modules', name)
    if (existsSync(join(candidate, 'package.json'))) {
      try {
        return realpathSync(candidate)
      } catch {
        return candidate
      }
    }
    const parent = dirname(dir)
    if (parent === dir) return null
    dir = parent
  }
}

function readPkg(pkgDir) {
  try {
    return JSON.parse(readFileSync(join(pkgDir, 'package.json'), 'utf8'))
  } catch {
    return null
  }
}

// Walk pi's dependency graph and return the sorted asarUnpack globs plus stats.
// Pure: reads node_modules, writes nothing.
export function computeUnpackGlobs() {
  const visitedDirs = new Set()
  const collected = new Map() // realDir -> package name

  const queue = ROOTS.map((name) => [name, WIN_ROOT])
  while (queue.length > 0) {
    const [name, fromDir] = queue.shift()
    const pkgDir = resolvePackageDir(name, fromDir)
    if (!pkgDir) continue // optional/platform dep not installed here — skip cleanly
    if (visitedDirs.has(pkgDir)) continue
    visitedDirs.add(pkgDir)
    collected.set(pkgDir, name)
    const pkg = readPkg(pkgDir)
    if (!pkg) continue
    const deps = { ...(pkg.dependencies || {}), ...(pkg.optionalDependencies || {}) }
    for (const dep of Object.keys(deps)) queue.push([dep, pkgDir])
  }

  const globs = new Set()
  const skippedCovered = new Set()
  for (const [realDir, name] of collected) {
    if (isAlreadyCovered(name)) {
      skippedCovered.add(name)
      continue
    }
    const rel = relative(WIN_ROOT, realDir).split(sep).join('/')
    if (!rel.startsWith('node_modules/')) continue // resolved outside the tree — ignore
    globs.add(`${rel}/**`)
  }

  return {
    globs: [...globs].sort(),
    closureSize: collected.size,
    coveredCount: skippedCovered.size
  }
}

function writeGenerated() {
  const { globs, closureSize, coveredCount } = computeUnpackGlobs()
  mkdirSync(dirname(GENERATED_FILE), { recursive: true })
  writeFileSync(GENERATED_FILE, JSON.stringify(globs, null, 2) + '\n')
  console.log(
    `[gen-pimono-unpack] wrote ${globs.length} globs to build/pimono-asar-unpack.generated.json ` +
      `(${closureSize} packages in closure, ${coveredCount} already covered).`
  )
}

// CLI entrypoint (only when run directly, never on import).
if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  if (process.argv.includes('--print')) {
    const { globs, closureSize, coveredCount } = computeUnpackGlobs()
    for (const g of globs) console.log(g)
    console.error(
      `\n[gen-pimono-unpack] ${globs.length} globs; ${closureSize} packages in closure; ` +
        `${coveredCount} skipped (already covered).`
    )
  } else {
    writeGenerated()
  }
}
