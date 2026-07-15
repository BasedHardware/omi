// captureScreenToFile() — the raw Windows screen grab. Electron is mocked with a
// fake desktopCapturer/screen and a real temp userData dir, so we exercise source
// selection, the JPEG file write + path return, temp-file pruning, and the failure
// path without a display.

import { describe, it, expect, beforeEach, afterAll, vi } from 'vitest'
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  rmSync,
  utimesSync,
  writeFileSync
} from 'fs'
import { tmpdir } from 'os'
import { basename, join } from 'path'

const userDataDir = mkdtempSync(join(tmpdir(), 'omi-capture-test-'))

// Mutable capture behavior the tests flip. Hoisted so vi.mock can close over it.
const state = vi.hoisted(() => ({
  sources: [] as Array<{
    id: string
    display_id: string
    thumbnail: { isEmpty: () => boolean; toJPEG: (q: number) => Buffer }
  }>,
  cursorDisplayId: 1,
  throwOnCursor: false
}))

vi.mock('electron', () => ({
  app: { getPath: (): string => userDataDir },
  desktopCapturer: {
    getSources: async (): Promise<typeof state.sources> => state.sources
  },
  screen: {
    getCursorScreenPoint: (): { x: number; y: number } => {
      if (state.throwOnCursor) throw new Error('no display')
      return { x: 10, y: 10 }
    },
    getDisplayNearestPoint: (): {
      id: number
      size: { width: number; height: number }
      scaleFactor: number
    } => ({
      id: state.cursorDisplayId,
      size: { width: 1600, height: 900 },
      scaleFactor: 2
    }),
    on: (): void => {}
  }
}))

import { captureScreenToFile } from './screenCapture'

const jpegBytes = Buffer.from([0xff, 0xd8, 0xff, 0xd9]) // token JPEG SOI/EOI
function fakeSource(id: string, displayId: number, empty = false): (typeof state.sources)[number] {
  return {
    id,
    display_id: String(displayId),
    thumbnail: { isEmpty: () => empty, toJPEG: () => (empty ? Buffer.alloc(0) : jpegBytes) }
  }
}

const screenshotsDir = join(userDataDir, 'chat-screenshots')

beforeEach(() => {
  state.sources = [fakeSource('screen:0', 1), fakeSource('screen:1', 2)]
  state.cursorDisplayId = 1
  state.throwOnCursor = false
  rmSync(screenshotsDir, { recursive: true, force: true })
})

afterAll(() => rmSync(userDataDir, { recursive: true, force: true }))

describe('captureScreenToFile', () => {
  it('writes a JPEG under the cursor display and returns its path', async () => {
    const path = await captureScreenToFile()
    expect(path.startsWith(screenshotsDir)).toBe(true)
    expect(path.endsWith('.jpg')).toBe(true)
    expect(existsSync(path)).toBe(true)
  })

  it('selects the source matching the display under the cursor', async () => {
    // Only display 2 has a capturable frame; the cursor is on display 2.
    state.cursorDisplayId = 2
    state.sources = [fakeSource('screen:0', 1, true), fakeSource('screen:1', 2)]
    const path = await captureScreenToFile()
    expect(existsSync(path)).toBe(true) // picked screen:1 (non-empty), not the empty screen:0
  })

  it('prunes stale screenshots but keeps the fresh capture', async () => {
    mkdirSync(screenshotsDir, { recursive: true })
    const stale = join(screenshotsDir, 'screenshot-1.jpg')
    writeFileSync(stale, jpegBytes)
    const twoHoursAgo = Date.now() / 1000 - 2 * 60 * 60
    utimesSync(stale, twoHoursAgo, twoHoursAgo)

    const fresh = await captureScreenToFile()

    expect(existsSync(stale)).toBe(false) // pruned (older than 1h)
    expect(existsSync(fresh)).toBe(true)
    const remaining = readdirSync(screenshotsDir).filter((f) => f.endsWith('.jpg'))
    expect(remaining).toEqual([basename(fresh)])
  })

  it('throws when no display can be captured', async () => {
    state.sources = []
    await expect(captureScreenToFile()).rejects.toThrow('Failed to capture screen')
  })

  it('throws when the captured frame is empty', async () => {
    state.sources = [fakeSource('screen:0', 1, true)]
    await expect(captureScreenToFile()).rejects.toThrow('Failed to capture screen')
  })
})
