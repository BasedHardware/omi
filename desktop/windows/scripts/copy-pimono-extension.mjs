#!/usr/bin/env node
// Copies the pi-mono omi-provider extension source into out/main so a packaged
// build can find it.
//
// piMono.ts resolveBundledExtension() returns
//   join(dirname(import.meta.url), 'pi-mono-extension', 'index.ts')
// i.e. it expects the extension to sit NEXT TO the compiled main bundle at
// out/main/pi-mono-extension/index.ts. But the extension is a raw .ts source dir
// (pi loads it on the fly via jiti — no precompile), and electron-vite only emits
// the main bundle; it never copies this sibling source tree. Without this step a
// packaged build has no extension file and `pi --provider omi` fails to register
// the Omi provider.
//
// Run as part of `build` (after electron-vite build, before electron-builder
// packs). electron-builder.config.mjs asarUnpacks out/main/pi-mono-extension/**
// so pi (a plain-Node child that cannot read from asar) can load it. jiti
// resolves the extension's `@earendil-works/pi-ai` imports by walking up to the
// asarUnpacked root node_modules.
//
//   node scripts/copy-pimono-extension.mjs

import { copyFileSync, existsSync, mkdirSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WIN_ROOT = join(HERE, '..')
const SRC = join(WIN_ROOT, 'src', 'main', 'codingAgent', 'pi-mono-extension')
const DEST = join(WIN_ROOT, 'out', 'main', 'pi-mono-extension')

if (!existsSync(SRC)) {
  console.error(`[copy-pimono-extension] source dir missing: ${SRC}`)
  process.exit(1)
}
if (!existsSync(join(WIN_ROOT, 'out', 'main'))) {
  console.error(
    '[copy-pimono-extension] out/main does not exist — run `electron-vite build` first.'
  )
  process.exit(1)
}

mkdirSync(DEST, { recursive: true })

// Copy the runtime files only — skip test files (never loaded by pi).
const copied = []
for (const name of readdirSync(SRC)) {
  if (name.endsWith('.test.ts')) continue
  copyFileSync(join(SRC, name), join(DEST, name))
  copied.push(name)
}

// index.ts is the entrypoint resolveBundledExtension() targets — assert it landed.
if (!copied.includes('index.ts')) {
  console.error(`[copy-pimono-extension] index.ts was not copied (found: ${copied.join(', ')})`)
  process.exit(1)
}

console.log(
  `[copy-pimono-extension] copied ${copied.length} files to out/main/pi-mono-extension/: ${copied.join(', ')}`
)
