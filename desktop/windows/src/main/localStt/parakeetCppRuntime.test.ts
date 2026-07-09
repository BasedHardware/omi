import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdir, mkdtemp, rm, writeFile } from 'fs/promises'
import { dirname, join } from 'path'
import { tmpdir } from 'os'
import {
  ensureManagedParakeetRuntime,
  getManagedParakeetStatus,
  resetManagedParakeetRuntimeStateForTests
} from './parakeetCppRuntime'

let root = ''

beforeEach(async () => {
  resetManagedParakeetRuntimeStateForTests()
  root = await mkdtemp(join(tmpdir(), 'omi-parakeet-runtime-'))
})

afterEach(async () => {
  resetManagedParakeetRuntimeStateForTests()
  if (root) await rm(root, { recursive: true, force: true })
  root = ''
})

describe('managed parakeet.cpp runtime', () => {
  it('downloads CUDA runtime assets and the GGUF model into app-owned storage', async () => {
    const downloads: string[] = []
    const extracts: string[] = []
    const deps = {
      env: {
        OMI_LOCAL_STT_RELEASE_BASE: 'https://downloads.example/parakeet',
        OMI_LOCAL_STT_MODEL_URL: 'https://models.example/tdt.gguf'
      },
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => true,
      downloadFile: async (url: string, destination: string): Promise<void> => {
        downloads.push(url)
        await mkdir(dirname(destination), { recursive: true })
        await writeFile(destination, 'asset')
      },
      extractZip: async (zipPath: string, destination: string): Promise<void> => {
        extracts.push(zipPath)
        await mkdir(destination, { recursive: true })
        await writeFile(join(destination, 'parakeet-cli.exe'), 'exe')
      }
    }

    const runtime = await ensureManagedParakeetRuntime(deps)
    const status = await getManagedParakeetStatus(deps)

    expect(runtime).toMatchObject({
      variant: 'cuda',
      exePath: join(root, 'bin', 'parakeet-cli.exe'),
      modelPath: join(root, 'models', 'tdt_ctc-110m-q8_0.gguf')
    })
    expect(downloads).toEqual([
      'https://downloads.example/parakeet/parakeet-v0.3.2-bin-win-cuda-x64.zip',
      'https://downloads.example/parakeet/cudart-parakeet-bin-win-cuda-x64.zip',
      'https://models.example/tdt.gguf'
    ])
    expect(extracts).toHaveLength(2)
    expect(status.available).toBe(true)
    expect(status.runtime.installState).toBe('installed')
  })

  it('rejects without downloading anything when installs are not allowed', async () => {
    const downloads: string[] = []
    const deps = {
      env: {
        OMI_LOCAL_STT_RELEASE_BASE: 'https://downloads.example/parakeet',
        OMI_LOCAL_STT_MODEL_URL: 'https://models.example/tdt.gguf'
      },
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => true,
      downloadFile: async (url: string): Promise<void> => {
        downloads.push(url)
        throw new Error('download must not be attempted when allowInstall is false')
      },
      extractZip: async (): Promise<void> => undefined
    }

    await expect(ensureManagedParakeetRuntime(deps, { allowInstall: false })).rejects.toThrow(
      /not installed/
    )
    expect(downloads).toEqual([])

    // The refusal must not poison the status: nothing was attempted, so the
    // runtime still reports installable, not an install error.
    const status = await getManagedParakeetStatus(deps)
    expect(status.available).toBe(false)
    expect(status.runtime.installState).toBe('not_installed')
    expect(status.runtime.canInstall).toBe(true)
  })

  it('resolves an already-installed runtime even when installs are not allowed', async () => {
    const deps = {
      env: {
        OMI_LOCAL_STT_RELEASE_BASE: 'https://downloads.example/parakeet',
        OMI_LOCAL_STT_MODEL_URL: 'https://models.example/tdt.gguf'
      },
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => true,
      downloadFile: async (): Promise<void> => {
        throw new Error('download must not be attempted for an installed runtime')
      },
      extractZip: async (): Promise<void> => undefined
    }

    await mkdir(join(root, 'bin'), { recursive: true })
    await writeFile(join(root, 'bin', 'parakeet-cli.exe'), 'exe')
    await mkdir(join(root, 'models'), { recursive: true })
    await writeFile(join(root, 'models', 'tdt_ctc-110m-q8_0.gguf'), 'model')

    const runtime = await ensureManagedParakeetRuntime(deps, { allowInstall: false })

    expect(runtime).toMatchObject({
      exePath: join(root, 'bin', 'parakeet-cli.exe'),
      modelPath: join(root, 'models', 'tdt_ctc-110m-q8_0.gguf')
    })
  })

  it('uses the CPU artifact only when explicitly forced for test/dev', async () => {
    const downloads: string[] = []
    const deps = {
      env: {
        OMI_LOCAL_STT_RUNTIME_VARIANT: 'cpu',
        OMI_LOCAL_STT_RELEASE_BASE: 'https://downloads.example/parakeet',
        OMI_LOCAL_STT_MODEL_URL: 'https://models.example/tdt.gguf'
      } as NodeJS.ProcessEnv,
      platform: 'win32',
      arch: 'x64',
      rootDir: root,
      detectNvidiaGpu: async () => false,
      downloadFile: async (url: string, destination: string): Promise<void> => {
        downloads.push(url)
        await mkdir(dirname(destination), { recursive: true })
        await writeFile(destination, 'asset')
      },
      extractZip: async (_zipPath: string, destination: string): Promise<void> => {
        await mkdir(destination, { recursive: true })
        await writeFile(join(destination, 'parakeet-cli.exe'), 'exe')
      }
    }

    const runtime = await ensureManagedParakeetRuntime(deps)

    expect(runtime.variant).toBe('cpu')
    expect(downloads).toEqual([
      'https://downloads.example/parakeet/parakeet-v0.3.2-bin-win-cpu-x64.zip',
      'https://models.example/tdt.gguf'
    ])
  })
})
