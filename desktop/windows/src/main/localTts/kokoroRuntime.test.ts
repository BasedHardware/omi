import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { dirname, join } from 'path'
import {
  getManagedKokoroStatus,
  resetManagedKokoroRuntimeStateForTests,
  synthesizeWithManagedKokoro
} from './kokoroRuntime'

let root = ''

beforeEach(async () => {
  resetManagedKokoroRuntimeStateForTests()
  root = await mkdtemp(join(tmpdir(), 'omi-kokoro-runtime-'))
})

afterEach(async () => {
  resetManagedKokoroRuntimeStateForTests()
  vi.restoreAllMocks()
  if (root) await rm(root, { recursive: true, force: true })
  root = ''
})

describe('managed Kokoro runtime', () => {
  it('loads Kokoro into app-owned storage and writes synthesized WAV output', async () => {
    const transformersEnv = {
      cacheDir: '',
      allowRemoteModels: false,
      allowLocalModels: false,
      useFSCache: false
    }
    const fromPretrained = vi.fn(async () => ({
      generate: vi.fn(async (text: string, options?: { voice?: string; speed?: number }) => ({
        save: async (filePath: string): Promise<void> => {
          await mkdir(dirname(filePath), { recursive: true })
          await writeFile(filePath, `RIFF:${text}:${options?.voice}:${options?.speed}`)
        }
      }))
    }))
    const deps = {
      env: { OMI_LOCAL_TTS_ALLOW_NON_WINDOWS: '1' },
      platform: 'linux',
      arch: 'x64',
      rootDir: root,
      loadTransformers: async () => ({ env: transformersEnv }),
      loadKokoro: async () => ({ KokoroTTS: { from_pretrained: fromPretrained } })
    }

    const initialStatus = await getManagedKokoroStatus(deps)
    const result = await synthesizeWithManagedKokoro(
      { text: 'Hello from local TTS', voice: 'af_heart', speed: 1.2 },
      deps
    )
    const readyStatus = await getManagedKokoroStatus(deps)

    expect(initialStatus.runtime.installState).toBe('not_installed')
    expect(transformersEnv.cacheDir).toBe(join(root, 'models'))
    expect(transformersEnv.allowRemoteModels).toBe(true)
    expect(transformersEnv.useFSCache).toBe(true)
    expect(fromPretrained).toHaveBeenCalledWith('onnx-community/Kokoro-82M-v1.0-ONNX', {
      dtype: 'q8',
      device: 'cpu'
    })
    expect(result.mimeType).toBe('audio/wav')
    expect(result.audioUrl).toMatch(/^file:/)
    await expect(readFile(result.audioPath, 'utf8')).resolves.toContain('Hello from local TTS')
    expect(readyStatus.available).toBe(true)
    expect(readyStatus.runtime.installState).toBe('installed')
  })

  it('reports unsupported when disabled and does not offer install', async () => {
    const status = await getManagedKokoroStatus({
      env: { OMI_LOCAL_TTS_DISABLED: '1' },
      platform: 'win32',
      arch: 'x64',
      rootDir: root
    })

    expect(status.available).toBe(false)
    expect(status.runtime.installState).toBe('unsupported')
    expect(status.runtime.canInstall).toBe(false)
    expect(status.reason).toBe('local TTS disabled')
  })

  it('keeps status in error when synthesis fails', async () => {
    const deps = {
      env: { OMI_LOCAL_TTS_ALLOW_NON_WINDOWS: '1' },
      platform: 'linux',
      arch: 'x64',
      rootDir: root,
      loadTransformers: async () => ({
        env: {
          cacheDir: '',
          allowRemoteModels: false,
          allowLocalModels: false,
          useFSCache: false
        }
      }),
      loadKokoro: async () => ({
        KokoroTTS: {
          from_pretrained: async () => {
            throw new Error('model load failed')
          }
        }
      })
    }

    await expect(synthesizeWithManagedKokoro({ text: 'hello' }, deps)).rejects.toThrow(
      'model load failed'
    )
    const status = await getManagedKokoroStatus(deps)

    expect(status.available).toBe(false)
    expect(status.runtime.installState).toBe('error')
    expect(status.reason).toBe('model load failed')
  })
})
