import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import { getLocalSttStatus } from './status'
import { resetManagedParakeetRuntimeStateForTests } from './parakeetCppRuntime'

let root = ''

beforeEach(async () => {
  resetManagedParakeetRuntimeStateForTests()
  root = await mkdtemp(join(tmpdir(), 'omi-local-stt-status-'))
})

afterEach(async () => {
  resetManagedParakeetRuntimeStateForTests()
  if (root) await rm(root, { recursive: true, force: true })
  root = ''
})

describe('local STT status', () => {
  it('ignores externally configured localhost services and reports managed first-use install', async () => {
    const status = await getLocalSttStatus({
      env: { OMI_LOCAL_PARAKEET_URL: 'http://127.0.0.1:9000' } as NodeJS.ProcessEnv,
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => true,
      now: () => 123
    })

    expect(status).toMatchObject({
      healthy: false,
      available: false,
      nvidiaAvailable: true,
      managed: true,
      runtime: {
        kind: 'parakeet.cpp',
        installState: 'not_installed',
        variant: 'cuda',
        canInstall: true
      },
      checkedAt: 123
    })
    expect(status.configuredUrl).toBeUndefined()
    expect(status.healthUrl).toBeUndefined()
    expect(status.reason).toBe('Local Parakeet will install on first use')
  })

  it('is available when the app-owned runtime and model are installed', async () => {
    await mkdir(join(root, 'bin'), { recursive: true })
    await mkdir(join(root, 'models'), { recursive: true })
    await writeFile(join(root, 'bin', 'parakeet-cli.exe'), 'exe')
    await writeFile(join(root, 'models', 'tdt_ctc-110m-q8_0.gguf'), 'model')

    const status = await getLocalSttStatus({
      env: {},
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => true
    })

    expect(status).toMatchObject({
      healthy: true,
      available: true,
      nvidiaAvailable: true,
      managed: true,
      runtime: {
        installState: 'installed',
        variant: 'cuda',
        canInstall: true
      }
    })
  })

  it('blocks auto-local on Windows when NVIDIA is missing', async () => {
    const status = await getLocalSttStatus({
      env: {},
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => false
    })

    expect(status.available).toBe(false)
    expect(status.healthy).toBe(false)
    expect(status.runtime.installState).toBe('unsupported')
    expect(status.runtime.canInstall).toBe(false)
    expect(status.reason).toBe('NVIDIA GPU not detected')
  })

  it('fails closed when local STT is disabled', async () => {
    const status = await getLocalSttStatus({
      env: { OMI_LOCAL_STT_DISABLED: '1' },
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => true
    })

    expect(status.available).toBe(false)
    expect(status.healthy).toBe(false)
    expect(status.runtime.canInstall).toBe(false)
    expect(status.reason).toBe('local STT disabled')
  })
})
