#!/usr/bin/env node
// Bundles the pi-mono omi-provider extension into a single self-contained file
// next to the packaged main bundle.
//
// piMono.ts resolveBundledExtension() returns
//   join(dirname(import.meta.url), 'pi-mono-extension', 'index.ts')
// i.e. it expects the extension at out/main/pi-mono-extension/index.ts. pi loads
// that file on the fly via jiti (no precompile) in the spawned plain-Node child.
//
// WHY BUNDLE, not copy: the extension source is NOT self-contained. index.ts
// imports `../../agentKernel/omiToolManifest` (which pulls in controlToolManifest)
// and `./node-tools` — a relative reach into the app's own TypeScript tree. In
// dev/test that resolves because the extension loads from its SOURCE location next
// to src/main/agentKernel. But a packaged build only has the compiled main bundle
// (electron-vite inlines agentKernel INTO index.js — those sibling source files do
// not exist on disk), so a plain copy of the extension dir fails at load with
// `Cannot find module '../../agentKernel/omiToolManifest'`. (This was caught by the
// packaged-spawn smoke — verify-pimono-packaged-spawn.mjs.)
//
// esbuild inlines every app-source import (node-tools, omiToolManifest,
// controlToolManifest — all pure: node builtins + types/data) into one file, and
// keeps `@earendil-works/*` EXTERNAL so pi/jiti resolves them at runtime from the
// asarUnpacked node_modules. Output is ESM named index.ts (jiti loads valid JS as
// TS). esbuild fails loud if a new import can't be resolved — a build-time guard
// against the extension quietly gaining another unbundleable dependency.
//
// Wired into `build` (after electron-vite build, before electron-builder packs);
// electron-builder.config.mjs asarUnpacks out/main/pi-mono-extension/**.
//
//   node scripts/bundle-pimono-extension.mjs

import { build } from 'esbuild'
import { copyFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WIN_ROOT = join(HERE, '..')
const SRC_DIR = join(WIN_ROOT, 'src', 'main', 'codingAgent', 'pi-mono-extension')
const SRC_ENTRY = join(SRC_DIR, 'index.ts')
const DEST_DIR = join(WIN_ROOT, 'out', 'main', 'pi-mono-extension')
const DEST_ENTRY = join(DEST_DIR, 'index.ts')

if (!existsSync(SRC_ENTRY)) {
  console.error(`[bundle-pimono-extension] source entry missing: ${SRC_ENTRY}`)
  process.exit(1)
}
if (!existsSync(join(WIN_ROOT, 'out', 'main'))) {
  console.error(
    '[bundle-pimono-extension] out/main does not exist — run `electron-vite build` first.'
  )
  process.exit(1)
}

mkdirSync(DEST_DIR, { recursive: true })

try {
  await build({
    entryPoints: [SRC_ENTRY],
    outfile: DEST_ENTRY,
    bundle: true,
    format: 'esm',
    platform: 'node',
    target: 'node20',
    // pi/jiti resolves these from the asarUnpacked node_modules at runtime; do NOT
    // inline them (they are large and would drag pi's own runtime into the bundle).
    external: ['@earendil-works/*'],
    logLevel: 'warning',
    legalComments: 'none'
  })
} catch (err) {
  console.error(
    `[bundle-pimono-extension] esbuild failed: ${err instanceof Error ? err.message : err}`
  )
  process.exit(1)
}

// Keep the package.json next to the bundle — its `"type": "module"` removes any
// CJS/ESM ambiguity for jiti, and it names the extension.
const pkg = join(SRC_DIR, 'package.json')
if (existsSync(pkg)) copyFileSync(pkg, join(DEST_DIR, 'package.json'))

if (!existsSync(DEST_ENTRY)) {
  console.error('[bundle-pimono-extension] bundle did not produce index.ts')
  process.exit(1)
}
console.log(
  '[bundle-pimono-extension] bundled extension → out/main/pi-mono-extension/index.ts (self-contained, @earendil-works external)'
)
