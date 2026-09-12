#!/usr/bin/env node
// Runtime guard for issue #10738. electron-builder 26.8.1's pnpm dependency
// collection packaged debug (used by Sentry) but omitted its hoisted `ms`
// dependency. The installed tree and source build both passed; the shipped app
// crashed on launch. Newer builders include the dependency, and this probe keeps
// that final-artifact contract from regressing.
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
    'const { join, resolve } = require("node:path");',
    'const appRoot = process.env.OMI_PACKAGED_APP_ROOT;',
    'const manifestPath = join(appRoot, "package.json");',
    'const manifestRequire = createRequire(manifestPath);',
    'const manifest = manifestRequire("./package.json");',
    'if (typeof manifest.main !== "string" || !manifest.main) throw new Error("packaged manifest has no main entry");',
    'const mainEntry = resolve(appRoot, manifest.main);',
    'manifestRequire.resolve(mainEntry);',
    'const runtimeRequire = createRequire(mainEntry);',
    'const sentryMainPath = runtimeRequire.resolve("@sentry/electron/main");',
    'const sentryRequire = createRequire(sentryMainPath);',
    // debug loads `ms` from src/common.js. Resolving from Sentry's packaged entry
    // exercises the exact dependency boundary that failed in #10738 without
    // initializing Electron or sending telemetry from the release runner.
    'const debug = sentryRequire("debug");',
    'if (typeof debug !== "function") throw new Error("debug did not export a function");',
    'const msPath = sentryRequire.resolve("ms");',
    `console.log("${SUCCESS_MARKER} " + JSON.stringify({ mainEntry, sentryMainPath, msPath }));`
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
      OMI_PACKAGED_APP_ROOT: appAsarPath
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
  const markerLine = output.split(/\r?\n/).find((line) => line.startsWith(`${SUCCESS_MARKER} `))
  if (!markerLine) {
    throw new Error(`packaged main dependency probe did not report success:\n${output}`)
  }

  let details
  try {
    details = JSON.parse(markerLine.slice(SUCCESS_MARKER.length + 1))
  } catch {
    throw new Error(`packaged main dependency probe reported malformed details:\n${output}`)
  }
  if (
    typeof details?.mainEntry !== 'string' ||
    typeof details?.sentryMainPath !== 'string' ||
    typeof details?.msPath !== 'string'
  ) {
    throw new Error(`packaged main dependency probe reported incomplete details:\n${output}`)
  }

  return { executablePath, ...details, output }
}

const invokedAsScript =
  process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))

if (invokedAsScript) {
  try {
    const result = verifyPackagedMainRuntime()
    console.log('[verify-packaged-main] PASS - packaged Sentry/debug runtime resolves ms.')
    console.log(`  binary: ${result.executablePath}`)
    console.log(`  main:   ${result.mainEntry}`)
    console.log(`  sentry: ${result.sentryMainPath}`)
    console.log(`  ms:     ${result.msPath}`)
  } catch (error) {
    console.error(
      `\n[verify-packaged-main] FAIL - packaged app would crash like #10738:\n${
        error instanceof Error ? error.message : String(error)
      }\n`
    )
    process.exitCode = 1
  }
}
