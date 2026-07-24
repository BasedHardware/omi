import { describe, it, expect } from 'vitest'

// Exercise the pure `sanitize` via the module's coercion contract. #10489 added
// `highResCapture`; these pin that it defaults OFF and only an explicit `true`
// opts in — so an old settings file (written before the field existed) keeps the
// perf-tuned baseline rather than silently enabling the higher-cost profile.
//
// sanitize is not exported, so drive it through the persisted-read path with a
// mocked file. Electron's `app.getPath` and the fs are stubbed at import time.
import { vi } from 'vitest'

let fileContents = ''
vi.mock('electron', () => ({ app: { getPath: () => '/tmp' } }))
vi.mock('fs', () => ({
  readFileSync: () => {
    if (fileContents === '__throw__') throw new Error('no file')
    return fileContents
  },
  writeFileSync: () => undefined
}))

const { getPersistedRewindSettings } = await import('./rewindSettings')

function read(raw: unknown): ReturnType<typeof getPersistedRewindSettings> {
  fileContents = JSON.stringify(raw)
  return getPersistedRewindSettings()
}

describe('rewindSettings highResCapture', () => {
  it('defaults OFF when the field is absent (pre-existing settings file)', () => {
    expect(read({ captureEnabled: true, intervalMs: 1000 }).highResCapture).toBe(false)
  })

  it('defaults OFF on a missing/corrupt file', () => {
    fileContents = '__throw__'
    expect(getPersistedRewindSettings().highResCapture).toBe(false)
  })

  it('only an explicit true opts in', () => {
    expect(read({ highResCapture: true }).highResCapture).toBe(true)
    expect(read({ highResCapture: 'yes' as unknown as boolean }).highResCapture).toBe(false)
    expect(read({ highResCapture: false }).highResCapture).toBe(false)
  })
})
