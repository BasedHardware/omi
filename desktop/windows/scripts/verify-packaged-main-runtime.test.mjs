import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  assertPathInsidePackagedRoot,
  packagedRuntimeDriver,
  verifyPackagedMainRuntime
} from './verify-packaged-main-runtime.mjs'

const fixtures = []

function makePackagedFixture({ executableName = 'omi-windows.exe' } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'omi-packaged-main-'))
  fixtures.push(root)
  const resources = join(root, 'resources')
  mkdirSync(resources)
  writeFileSync(join(root, executableName), 'fixture')
  writeFileSync(join(resources, 'app.asar'), 'fixture')
  return root
}

afterEach(() => {
  vi.restoreAllMocks()
  while (fixtures.length > 0) {
    rmSync(fixtures.pop(), { recursive: true, force: true })
  }
})

describe('packaged main runtime guard', () => {
  it('loads debug from the packaged main entry so its ms dependency is exercised', () => {
    const unpackedDir = makePackagedFixture()
    const mainEntry = join(unpackedDir, 'resources', 'app.asar', 'out', 'main', 'index.js')
    const sentryMainPath = join(
      unpackedDir,
      'resources',
      'app.asar',
      'node_modules',
      '@sentry',
      'electron',
      'main',
      'index.js'
    )
    const msPath = join(unpackedDir, 'resources', 'app.asar', 'node_modules', 'ms', 'index.js')
    const spawn = vi.fn(() => ({
      status: 0,
      stdout: `PACKAGED_MAIN_RUNTIME_OK ${JSON.stringify({ mainEntry, sentryMainPath, msPath })}\n`,
      stderr: ''
    }))

    const result = verifyPackagedMainRuntime({
      unpackedDir,
      spawn,
      sourceEnv: {
        Path: 'C:\\Windows\\System32',
        TEMP: 'C:\\Temp',
        AZURE_CLIENT_SECRET: 'must-not-reach-the-child'
      }
    })

    expect(result.output).toContain('PACKAGED_MAIN_RUNTIME_OK')
    expect(result.mainEntry).toBe(mainEntry)
    expect(result.sentryMainPath).toBe(sentryMainPath)
    expect(result.msPath).toBe(msPath)
    expect(spawn).toHaveBeenCalledOnce()
    const [executable, args, options] = spawn.mock.calls[0]
    expect(executable).toBe(join(unpackedDir, 'omi-windows.exe'))
    expect(args).toEqual(['-e', packagedRuntimeDriver()])
    expect(options.env.ELECTRON_RUN_AS_NODE).toBe('1')
    expect(options.env.Path).toBe('C:\\Windows\\System32')
    expect(options.env.TEMP).toBe('C:\\Temp')
    expect(options.env.AZURE_CLIENT_SECRET).toBeUndefined()
    expect(options.env.OMI_PACKAGED_APP_ROOT).toBe(join(unpackedDir, 'resources', 'app.asar'))
    expect(packagedRuntimeDriver()).toContain('manifest.main')
    expect(packagedRuntimeDriver()).toContain('@sentry/electron/main')
    expect(packagedRuntimeDriver()).toContain('debugRequire.resolve("ms")')
    expect(packagedRuntimeDriver()).toContain('ms resolved outside packaged app root')
  })

  it('rejects ms resolved from host node_modules outside app.asar', () => {
    const unpackedDir = makePackagedFixture()
    const appAsar = join(unpackedDir, 'resources', 'app.asar')
    const mainEntry = join(appAsar, 'out', 'main', 'index.js')
    const sentryMainPath = join(appAsar, 'node_modules', '@sentry', 'electron', 'main', 'index.js')
    const hostMsPath = join(unpackedDir, '..', 'node_modules', 'ms', 'index.js')
    const spawn = vi.fn(() => ({
      status: 0,
      stdout: `PACKAGED_MAIN_RUNTIME_OK ${JSON.stringify({
        mainEntry,
        sentryMainPath,
        msPath: hostMsPath
      })}\n`,
      stderr: ''
    }))

    expect(() => verifyPackagedMainRuntime({ unpackedDir, spawn })).toThrow(/ms resolved outside packaged app root/)
  })

  it('assertPathInsidePackagedRoot accepts paths under app.asar', () => {
    const appAsar = join(tmpdir(), 'win-unpacked', 'resources', 'app.asar')
    const msPath = join(appAsar, 'node_modules', 'ms', 'index.js')
    expect(() => assertPathInsidePackagedRoot(appAsar, msPath, 'ms')).not.toThrow()
  })

  it('assertPathInsidePackagedRoot rejects paths outside app.asar', () => {
    const appAsar = join(tmpdir(), 'win-unpacked', 'resources', 'app.asar')
    const hostMsPath = join(tmpdir(), 'node_modules', 'ms', 'index.js')
    expect(() => assertPathInsidePackagedRoot(appAsar, hostMsPath, 'ms')).toThrow(
      /ms resolved outside packaged app root/
    )
  })

  it('rejects a different executable instead of running an arbitrary build artifact', () => {
    const unpackedDir = makePackagedFixture({ executableName: 'larger-helper.exe' })
    const spawn = vi.fn()

    expect(() => verifyPackagedMainRuntime({ unpackedDir, spawn })).toThrow(/omi-windows\.exe/)
    expect(spawn).not.toHaveBeenCalled()
  })

  it('fails when the packaged debug chain cannot resolve ms', () => {
    const unpackedDir = makePackagedFixture()
    const spawn = vi.fn(() => ({
      status: 1,
      stdout: '',
      stderr: "Error: Cannot find module 'ms'"
    }))

    expect(() => verifyPackagedMainRuntime({ unpackedDir, spawn })).toThrow(
      /Cannot find module 'ms'/
    )
  })

  it('fails closed when the child exits without the success marker', () => {
    const unpackedDir = makePackagedFixture()
    const spawn = vi.fn(() => ({ status: 0, stdout: '', stderr: '' }))

    expect(() => verifyPackagedMainRuntime({ unpackedDir, spawn })).toThrow(
      /did not report success/
    )
  })

  it.each([
    ['not-json', /malformed details/],
    [JSON.stringify({ mainEntry: 'index.js' }), /incomplete details/]
  ])('fails closed on invalid success details: %s', (details, expected) => {
    const unpackedDir = makePackagedFixture()
    const spawn = vi.fn(() => ({
      status: 0,
      stdout: `PACKAGED_MAIN_RUNTIME_OK ${details}\n`,
      stderr: ''
    }))

    expect(() => verifyPackagedMainRuntime({ unpackedDir, spawn })).toThrow(expected)
  })
})
