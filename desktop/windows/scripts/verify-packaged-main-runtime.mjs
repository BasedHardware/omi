#!/usr/bin/env node
// Runtime guard for issue #10738. electron-builder's pnpm dependency collection
// packaged debug (used by Sentry) but omitted its hoisted `ms` dependency. The
// installed tree and source build both passed; the shipped app crashed on launch.
//
// Run this after electron-builder has produced dist/win-unpacked. The packaged
// Electron binary supplies the same ASAR-aware CommonJS loader used by the app,
// so loading debug from the packaged main entry exercises the failing boundary.

import { spawnSync } from 'node:child_process'
import { existsSync, lstatSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WINDOWS_ROOT = join(HERE, '..')
const DEFAULT_UNPACKED_DIR = join(WINDOWS_ROOT, 'dist', 'win-unpacked')
const SUCCESS_MARKER = 'PACKAGED_MAIN_RUNTIME_OK'
const PROBE_ENV_ALLOWLIST = new Set([
  'COMSPEC',
  'PATH',
  'PATHEXT',
  'SYSTEMROOT',
  'TEMP',
  'TMP',
  'WINDIR'
])

export function findPackagedExecutable(unpackedDir) {
  const unpackedRoot = resolve(unpackedDir)
  if (!existsSync(unpackedRoot)) {
    throw new Error(`unpacked build does not exist: ${unpackedRoot}`)
  }

  const executablePath = join(unpackedRoot, 'omi-windows.exe')
  if (!existsSync(executablePath)) {
    throw new Error(`packaged executable does not exist: ${executablePath}`)
  }

  const executableStats = lstatSync(executablePath)
  if (!executableStats.isFile() || executableStats.isSymbolicLink()) {
    throw new Error(`packaged executable is not a regular file: ${executablePath}`)
  }

  return executablePath
}

export function packagedRuntimeDriver() {
  return [
    'const { createRequire } = require("node:module");',
    'const runtimeRequire = createRequire(process.env.OMI_PACKAGED_MAIN_ENTRY);',
    // debug loads `ms` from src/common.js. This is the exact #10738 launch chain.
    'const debug = runtimeRequire("debug");',
    'if (typeof debug !== "function") throw new Error("debug did not export a function");',
    'const msPath = runtimeRequire.resolve("ms");',
    `console.log("${SUCCESS_MARKER} " + msPath);`
  ].join('\n')
}

export function verifyPackagedMainRuntime({
  unpackedDir = DEFAULT_UNPACKED_DIR,
  spawn = spawnSync,
  sourceEnv = process.env
} = {}) {
  const unpackedRoot = resolve(unpackedDir)
  const executablePath = findPackagedExecutable(unpackedRoot)
  const appAsarPath = join(unpackedRoot, 'resources', 'app.asar')
  if (!existsSync(appAsarPath)) {
    throw new Error(`packaged app archive does not exist: ${appAsarPath}`)
  }

  const mainEntry = join(appAsarPath, 'out', 'main', 'index.js')
  const env = {}
  for (const [key, value] of Object.entries(sourceEnv)) {
    if (value !== undefined && PROBE_ENV_ALLOWLIST.has(key.toUpperCase())) {
      env[key] = value
    }
  }

  const result = spawn(executablePath, ['-e', packagedRuntimeDriver()], {
    cwd: unpackedRoot,
    env: {
      ...env,
      ELECTRON_RUN_AS_NODE: '1',
      NODE_NO_WARNINGS: '1',
      OMI_PACKAGED_MAIN_ENTRY: mainEntry
    },
    encoding: 'utf8',
    timeout: 30_000,
    windowsHide: true
  })

  if (result.error) {
    throw new Error(`could not run packaged main dependency probe: ${result.error.message}`)
  }

  const output = `${result.stdout ?? ''}${result.stderr ?? ''}`
  if (result.status !== 0) {
    throw new Error(
      `packaged main dependency probe exited ${result.status ?? 'without a status'}:\n${output}`
    )
  }
  if (!output.includes(SUCCESS_MARKER)) {
    throw new Error(`packaged main dependency probe did not report success:\n${output}`)
  }

  return { executablePath, mainEntry, output }
}

const invokedAsScript =
  process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))

if (invokedAsScript) {
  try {
    const result = verifyPackagedMainRuntime()
    console.log('[verify-packaged-main] PASS - packaged Sentry/debug runtime resolves ms.')
    console.log(`  binary: ${result.executablePath}`)
    console.log(`  main:   ${result.mainEntry}`)
  } catch (error) {
    console.error(
      `\n[verify-packaged-main] FAIL - packaged app would crash like #10738:\n${
        error instanceof Error ? error.message : String(error)
      }\n`
    )
    process.exitCode = 1
  }
}
