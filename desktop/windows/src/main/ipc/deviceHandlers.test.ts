import { describe, it, expect, vi } from 'vitest'

/** Handlers registered with ipcMain.handle, so the guards can be invoked. */
const handlers = new Map<string, (event: { sender: unknown }, ...args: unknown[]) => unknown>()

vi.mock('electron', () => ({
  ipcMain: {
    handle: vi.fn((channel: string, handler: never) => handlers.set(channel, handler)),
    on: vi.fn()
  },
  BrowserWindow: { getAllWindows: () => [] }
}))
vi.mock('../appSettings', () => ({
  getAppSettings: () => ({
    device: { pairedDevice: null, autoReconnect: true, deviceListenEnabled: false }
  }),
  setAppSettings: (patch: unknown) => patch
}))

const {
  attachBluetoothChooser,
  isChooserPending,
  parseRecoveredAudio,
  registerDeviceHandlers,
  resolveChooserSelection,
  selectChooserDevice
} = await import('./deviceHandlers')

const CANDIDATES = [
  { deviceId: 'aa', deviceName: 'Omi CV1' },
  { deviceId: 'bb', deviceName: 'Bee' }
]

describe('resolveChooserSelection', () => {
  it('auto-answers only for a remembered device that is actually present', () => {
    expect(resolveChooserSelection(CANDIDATES, 'bb')).toBe('bb')
    // Remembered but not in range: the chooser stays open rather than answering
    // with a device that is not there.
    expect(resolveChooserSelection(CANDIDATES, 'zz')).toBeNull()
  })

  it('never auto-answers a fresh pairing', () => {
    expect(resolveChooserSelection(CANDIDATES, null)).toBeNull()
  })
})

/** Minimal webContents stub exposing only the chooser event. */
const fakeWc = (): {
  wc: never
  fire: (
    devices: Array<{ deviceId: string; deviceName: string }>,
    callback: (id: string) => void
  ) => boolean
} => {
  let handler:
    | ((
        event: { preventDefault: () => void },
        devices: Array<{ deviceId: string; deviceName: string }>,
        callback: (id: string) => void
      ) => void)
    | null = null
  const wc = {
    on: (_channel: string, cb: typeof handler) => {
      handler = cb
    }
  }
  return {
    wc: wc as never,
    fire: (devices, callback) => {
      let prevented = false
      handler?.({ preventDefault: () => (prevented = true) }, devices, callback)
      return prevented
    }
  }
}

describe('attachBluetoothChooser', () => {
  it('answers a reconnect immediately and never surfaces candidates', () => {
    const { wc, fire } = fakeWc()
    const shown: Array<Array<{ deviceId: string }>> = []
    attachBluetoothChooser(wc, {
      autoSelectId: () => 'bb',
      onCandidates: (c) => shown.push(c)
    })
    let answered: string | null = null
    const prevented = fire(CANDIDATES, (id) => (answered = id))
    expect(prevented).toBe(true)
    expect(answered).toBe('bb')
    expect(shown.length).toBe(0)
    expect(isChooserPending()).toBe(false)
  })

  it('streams candidates for a fresh pairing and waits for the pick', () => {
    const { wc, fire } = fakeWc()
    const shown: Array<Array<{ deviceId: string }>> = []
    attachBluetoothChooser(wc, {
      autoSelectId: () => null,
      onCandidates: (c) => shown.push(c)
    })
    let answered: string | null = null
    fire(CANDIDATES, (id) => (answered = id))
    expect(shown[0].map((c) => c.deviceId)).toEqual(['aa', 'bb'])
    // The page stays blocked on the chooser until a selection arrives.
    expect(answered).toBeNull()
    expect(isChooserPending()).toBe(true)

    selectChooserDevice('aa')
    expect(answered).toBe('aa')
    expect(isChooserPending()).toBe(false)
  })

  it('cancelling answers with the empty string Chromium expects', () => {
    const { wc, fire } = fakeWc()
    attachBluetoothChooser(wc, { autoSelectId: () => null, onCandidates: () => undefined })
    let answered: string | null = null
    fire(CANDIDATES, (id) => (answered = id))
    selectChooserDevice(null)
    expect(answered).toBe('')
  })

  it('a selection with no chooser open is ignored', () => {
    expect(() => selectChooserDevice('aa')).not.toThrow()
    expect(isChooserPending()).toBe(false)
  })
})

describe('parseRecoveredAudio', () => {
  const valid = {
    bytes: Uint8Array.from([1, 2, 3]),
    timerStart: 1_723_800_000,
    seconds: 180,
    totalFrames: 9000,
    codec: 'opus',
    sampleRate: 16_000,
    frameSize: 160,
    device: 'omi'
  }

  it('accepts a complete recording', () => {
    expect(parseRecoveredAudio(valid)).toEqual(valid)
  })

  it('accepts bytes that crossed IPC as an ArrayBuffer', () => {
    const parsed = parseRecoveredAudio({ ...valid, bytes: Uint8Array.from([9, 9]).buffer })
    expect(parsed?.bytes).toBeInstanceOf(Uint8Array)
    expect(Array.from(parsed?.bytes ?? [])).toEqual([9, 9])
  })

  it('rejects an empty or absent payload', () => {
    expect(parseRecoveredAudio({ ...valid, bytes: new Uint8Array(0) })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, bytes: undefined })).toBeNull()
    expect(parseRecoveredAudio(null)).toBeNull()
    expect(parseRecoveredAudio('recording')).toBeNull()
  })

  it('rejects a capture time that is not a positive whole second', () => {
    // The upload filename carries this timestamp and the server parses it; a
    // zero or fractional value becomes an upload that can never be placed.
    expect(parseRecoveredAudio({ ...valid, timerStart: 0 })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, timerStart: -1 })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, timerStart: 1.5 })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, timerStart: '1723800000' })).toBeNull()
  })

  it('rejects a recording with no duration, frames, rate or frame size', () => {
    expect(parseRecoveredAudio({ ...valid, seconds: 0 })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, totalFrames: 0 })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, sampleRate: 0 })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, frameSize: 0 })).toBeNull()
  })

  it('rejects an empty codec or capture source', () => {
    // Both go into the upload filename, which the server splits on underscores.
    expect(parseRecoveredAudio({ ...valid, codec: '' })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, device: '' })).toBeNull()
    expect(parseRecoveredAudio({ ...valid, codec: 20 })).toBeNull()
  })
})

describe('the recovered-audio channel', () => {
  const audio = {
    bytes: Uint8Array.from([1, 2, 3]),
    timerStart: 1_723_800_000,
    seconds: 180,
    totalFrames: 9000,
    codec: 'opus',
    sampleRate: 16_000,
    frameSize: 160,
    device: 'omi'
  }

  const wire = (): {
    invoke: (senderId: number, payload: unknown) => Promise<unknown>
    stored: unknown[]
  } => {
    handlers.clear()
    const stored: unknown[] = []
    const deviceWc = { id: 7, isDestroyed: () => false } as never
    registerDeviceHandlers(
      () => deviceWc,
      () => 1,
      async (a) => {
        stored.push(a)
        return 'stored'
      }
    )
    const handler = handlers.get('omi-device:store-recovered')!
    return {
      invoke: async (senderId, payload) =>
        handler({ sender: { id: senderId } }, payload) as Promise<unknown>,
      stored
    }
  }

  it('accepts recovered audio from the device window', async () => {
    const h = wire()
    expect(await h.invoke(7, audio)).toBe('stored')
    expect(h.stored.length).toBe(1)
  })

  it('refuses recovered audio from any other window', async () => {
    const h = wire()
    // Every renderer shares one preload. Without this guard the main window, or
    // any auxiliary one, could inject recordings that upload as the user's
    // conversations.
    expect(await h.invoke(1, audio)).toBe('failed')
    expect(await h.invoke(99, audio)).toBe('failed')
    expect(h.stored).toEqual([])
  })

  it('refuses a malformed payload even from the device window', async () => {
    const h = wire()
    expect(await h.invoke(7, { ...audio, timerStart: 0 })).toBe('failed')
    expect(await h.invoke(7, null)).toBe('failed')
    expect(h.stored).toEqual([])
  })

  it('reports failure when there is no offline log to store into', async () => {
    handlers.clear()
    registerDeviceHandlers(
      () => ({ id: 7, isDestroyed: () => false }) as never,
      () => 1
    )
    const handler = handlers.get('omi-device:store-recovered')!
    expect(await handler({ sender: { id: 7 } }, audio)).toBe('failed')
  })

  it('refuses recovered audio when there is no device window at all', async () => {
    handlers.clear()
    const stored: unknown[] = []
    registerDeviceHandlers(
      () => null,
      () => 1,
      async (a) => {
        stored.push(a)
        return 'stored'
      }
    )
    const handler = handlers.get('omi-device:store-recovered')!
    expect(await handler({ sender: { id: 7 } }, audio)).toBe('failed')
    expect(stored).toEqual([])
  })
})
