import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ScreenSynthFrameRow } from './screenSynthSql'

const h = vi.hoisted(() => ({
  handle: vi.fn(),
  listFrames: vi.fn(),
  getState: vi.fn(),
  updateState: vi.fn(),
  advanceWatermark: vi.fn(),
  recordRun: vi.fn()
}))

vi.mock('electron', () => ({ ipcMain: { handle: h.handle } }))
vi.mock('./db', () => ({ listScreenSynthFrames: h.listFrames }))
vi.mock('../screenSynth/state', () => ({
  getScreenSynthState: h.getState,
  updateScreenSynthState: h.updateState,
  advanceWatermark: h.advanceWatermark,
  recordRun: h.recordRun
}))

import {
  buildSpatialOcrText,
  isNearDuplicateScreenText,
  registerScreenSynthHandlers
} from './screenSynth'

function frame(overrides: Partial<ScreenSynthFrameRow> = {}): ScreenSynthFrameRow {
  return {
    ts: 1,
    app: 'Code',
    windowTitle: 'plan.md',
    processName: 'code.exe',
    ocrText: 'File Edit quarterly plan Save',
    ocrLinesJson: JSON.stringify([
      { text: 'File', x: 10, y: 20, w: 20, h: 10, confidence: 1 },
      { text: 'quarterly plan', x: 100, y: 200, w: 100, h: 20, confidence: 1 },
      { text: 'Edit', x: 20, y: 205, w: 40, h: 20, confidence: 1 },
      { text: 'Save', x: 10, y: 1050, w: 40, h: 10, confidence: 1 }
    ]),
    height: 1080,
    ...overrides
  }
}

beforeEach(() => vi.clearAllMocks())

describe('spatial OCR synthesis', () => {
  it('filters screen chrome, clusters within 10px, and orders each Markdown row left-to-right', () => {
    expect(buildSpatialOcrText(frame())).toBe('- Edit | quarterly plan')
  })

  it('falls back for malformed or incomplete geometry without reintroducing chrome-only layouts', () => {
    expect(buildSpatialOcrText(frame({ ocrLinesJson: '{bad json' }))).toBe(
      'File Edit quarterly plan Save'
    )
    expect(
      buildSpatialOcrText(
        frame({
          ocrText: 'one two three four five six seven eight nine ten',
          ocrLinesJson: JSON.stringify([
            { text: 'one', x: 10, y: 200, w: 20, h: 10, confidence: 1 }
          ])
        })
      )
    ).toBe('one two three four five six seven eight nine ten')
    expect(
      buildSpatialOcrText(
        frame({
          ocrText: 'alpha beta',
          ocrLinesJson: JSON.stringify([
            { text: 'alpha zeta', x: 10, y: 200, w: 80, h: 10, confidence: 1 }
          ])
        })
      )
    ).toBe('alpha beta')
    expect(
      buildSpatialOcrText(
        frame({
          ocrText: 'File Save',
          ocrLinesJson: JSON.stringify([
            { text: 'File', x: 10, y: 20, w: 20, h: 10, confidence: 1 },
            { text: 'Save', x: 10, y: 1050, w: 40, h: 10, confidence: 1 }
          ])
        })
      )
    ).toBe('')
  })

  it('uses the indexed private query and keeps duplicate tail timestamps as blank markers', async () => {
    h.getState.mockReturnValue({ watermarkTs: 40 })
    const first = frame({ ts: 41 })
    const nearDuplicate = frame({
      ts: 42,
      ocrText: 'File Edit quarterly plans Save',
      ocrLinesJson: JSON.stringify([
        { text: 'File', x: 10, y: 20, w: 20, h: 10, confidence: 1 },
        { text: 'quarterly plans', x: 100, y: 200, w: 100, h: 20, confidence: 1 },
        { text: 'Edit', x: 20, y: 205, w: 40, h: 20, confidence: 1 },
        { text: 'Save', x: 10, y: 1050, w: 40, h: 10, confidence: 1 }
      ])
    })
    const otherWindow = frame({ ts: 43, windowTitle: 'notes.md' })
    h.listFrames.mockReturnValue([first, nearDuplicate, otherWindow])
    vi.spyOn(Date, 'now').mockReturnValue(50)

    registerScreenSynthHandlers()
    const handler = h.handle.mock.calls.find(([name]) => name === 'screenSynth:framesSince')?.[1]
    expect(handler).toBeTypeOf('function')

    const result = await handler()
    expect(h.listFrames).toHaveBeenCalledWith(41, 50)
    expect(result).toEqual([
      {
        ts: 41,
        app: 'Code',
        windowTitle: 'plan.md',
        processName: 'code.exe',
        ocrText: '- Edit | quarterly plan'
      },
      {
        ts: 42,
        app: 'Code',
        windowTitle: 'plan.md',
        processName: 'code.exe',
        ocrText: ''
      },
      {
        ts: 43,
        app: 'Code',
        windowTitle: 'notes.md',
        processName: 'code.exe',
        ocrText: '- Edit | quarterly plan'
      }
    ])
    expect(isNearDuplicateScreenText('- Edit | quarterly plan', '- Edit | quarterly plans')).toBe(
      true
    )
    expect(isNearDuplicateScreenText('a'.repeat(100), `${'a'.repeat(92)}${'b'.repeat(8)}`)).toBe(
      false
    )
    expect(isNearDuplicateScreenText('a'.repeat(100), `${'a'.repeat(93)}${'b'.repeat(7)}`)).toBe(
      true
    )
    const shifted = 'ab'.repeat(50)
    expect(isNearDuplicateScreenText(shifted, `${shifted.slice(1)}${shifted[0]}`)).toBe(true)
  })
})
