import { afterEach, describe, expect, it, vi } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
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
    const spawn = vi.fn(() => ({
      status: 0,
      stdout: `PACKAGED_MAIN_RUNTIME_OK ${join(unpackedDir, 'node_modules', 'ms')}\n`,
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
    expect(spawn).toHaveBeenCalledOnce()
    const [executable, args, options] = spawn.mock.calls[0]
    expect(executable).toBe(join(unpackedDir, 'omi-windows.exe'))
    expect(args).toEqual(['-e', packagedRuntimeDriver()])
    expect(options.env.ELECTRON_RUN_AS_NODE).toBe('1')
    expect(options.env.Path).toBe('C:\\Windows\\System32')
    expect(options.env.TEMP).toBe('C:\\Temp')
    expect(options.env.AZURE_CLIENT_SECRET).toBeUndefined()
    expect(options.env.OMI_PACKAGED_MAIN_ENTRY).toBe(
      join(unpackedDir, 'resources', 'app.asar', 'out', 'main', 'index.js')
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
})
