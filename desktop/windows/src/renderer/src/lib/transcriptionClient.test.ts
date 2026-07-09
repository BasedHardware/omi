import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LocalSttStatus, SttMode } from '../../../shared/types'
import type { OmiListenCallbacks, OmiListenHandle } from './omiListenClient'
import { startOmiListen } from './omiListenClient'
import { getPreferences } from './preferences'
import { startTranscription } from './transcriptionClient'

vi.mock('./firebase', () => ({ auth: { currentUser: { uid: 'user-1' } } }))
vi.mock('./omiListenClient', () => ({ startOmiListen: vi.fn() }))
vi.mock('./preferences', () => ({ getPreferences: vi.fn() }))

const startOmiListenMock = vi.mocked(startOmiListen)
const getPreferencesMock = vi.mocked(getPreferences)

function sttStatus(overrides: { available: boolean; canInstall: boolean }): LocalSttStatus {
  return {
    backend: 'parakeet',
    healthy: overrides.available,
    available: overrides.available,
    nvidiaAvailable: true,
    managed: true,
    runtime: {
      kind: 'parakeet.cpp',
      installState: overrides.available ? 'installed' : 'not_installed',
      variant: 'cuda',
      model: 'tdt_ctc-110m-q8_0.gguf',
      canInstall: overrides.canInstall
    },
    checkedAt: 1
  }
}

function setup(args: { sttMode?: SttMode; status: LocalSttStatus }): void {
  getPreferencesMock.mockReturnValue({
    captionIntervalMs: 2000,
    showRecordingBadge: true,
    reduceMotion: false,
    language: 'en',
    chatHistoryMode: 'infinite',
    sttMode: args.sttMode
  })
  ;(globalThis as { window?: unknown }).window = {
    omi: { localSttStatus: vi.fn(async () => args.status) }
  }
  startOmiListenMock.mockImplementation(
    async (_source, cb: OmiListenCallbacks): Promise<OmiListenHandle> => {
      const handle = { stop: vi.fn(async () => undefined) }
      // Fire after the caller's .then() stored the handle, like the real client.
      setTimeout(() => cb.onConnected('omi'), 0)
      return handle
    }
  )
}

function attemptedModes(): Array<SttMode | undefined> {
  return startOmiListenMock.mock.calls.map((call) => call[2])
}

const callbacks = (): Parameters<typeof startTranscription>[1] => ({
  onLine: vi.fn(),
  onInterim: vi.fn(),
  onBackend: vi.fn(),
  onError: vi.fn()
})

afterEach(() => {
  vi.clearAllMocks()
  delete (globalThis as { window?: unknown }).window
})

describe('startTranscription backend selection', () => {
  it('auto with an installable-but-not-installed runtime uses cloud only and never requests local STT', async () => {
    setup({ sttMode: 'auto', status: sttStatus({ available: false, canInstall: true }) })
    const cb = callbacks()

    const handle = await startTranscription('mic', cb)
    await handle.stop()

    expect(attemptedModes()).toEqual(['cloud'])
    expect(cb.onBackend).toHaveBeenCalledWith('omi')
    expect(cb.onError).not.toHaveBeenCalled()
  })

  it('missing sttMode preference behaves like auto and stays on cloud when local is only installable', async () => {
    setup({ sttMode: undefined, status: sttStatus({ available: false, canInstall: true }) })

    const handle = await startTranscription('mic', callbacks())
    await handle.stop()

    expect(attemptedModes()).toEqual(['cloud'])
  })

  it('auto with an installed runtime tries local first, tagged as auto so main cannot install', async () => {
    setup({ sttMode: 'auto', status: sttStatus({ available: true, canInstall: true }) })

    const handle = await startTranscription('mic', callbacks())
    await handle.stop()

    expect(attemptedModes()[0]).toBe('auto')
  })

  it('explicit local-parakeet preference requests local STT with install permitted', async () => {
    setup({
      sttMode: 'local-parakeet',
      status: sttStatus({ available: false, canInstall: true })
    })

    const handle = await startTranscription('mic', callbacks())
    await handle.stop()

    expect(attemptedModes()[0]).toBe('local-parakeet')
  })

  it('cloud preference does not touch local STT when the runtime is not installed', async () => {
    setup({ sttMode: 'cloud', status: sttStatus({ available: false, canInstall: true }) })

    const handle = await startTranscription('mic', callbacks())
    await handle.stop()

    expect(attemptedModes()).toEqual(['cloud'])
  })
})
