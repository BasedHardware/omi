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

/** Match Program.cs: persist pixel boxes as fractions of frame width/height. */
function normalizedLine(
  text: string,
  xPx: number,
  yPx: number,
  wPx: number,
  hPx: number,
  width = 1920,
  height = 1080,
  confidence = 1
) {
  return {
    text,
    x: xPx / width,
    y: yPx / height,
    w: wPx / width,
    h: hPx / height,
    confidence
  }
}

function frame(overrides: Partial<ScreenSynthFrameRow> = {}): ScreenSynthFrameRow {
  return {
    ts: 1,
    app: 'Code',
    windowTitle: 'plan.md',
    processName: 'code.exe',
    ocrText: 'File Edit quarterly plan Save',
    ocrLinesJson: JSON.stringify([
      normalizedLine('File', 10, 20, 20, 10),
      normalizedLine('quarterly plan', 100, 200, 100, 20),
      normalizedLine('Edit', 20, 205, 40, 20),
      normalizedLine('Save', 10, 1050, 40, 10)
    ]),
    width: 1920,
    height: 1080,
    ...overrides
  }
}

beforeEach(() => vi.clearAllMocks())

describe('spatial OCR synthesis', () => {
  it('filters screen chrome, clusters within 10px, and orders each Markdown row left-to-right', () => {
    expect(buildSpatialOcrText(frame())).toBe('- Edit | quarterly plan')
  })

  it('denormalizes Program.cs 0..1 boxes before chrome filtering (real production shape)', () => {
    // Reviewer fixture: 1080p menu bar at y=20px → ~0.0185, content at y=540px → 0.5.
    // Without denormalize, y<=1 fails the pixel chrome gate and synthesis returns ''.
    const productionShaped = frame({
      ocrText: 'File Edit quarterly plan Save',
      ocrLinesJson: JSON.stringify([
        { text: 'File', x: 10 / 1920, y: 20 / 1080, w: 20 / 1920, h: 10 / 1080, confidence: 1 },
        {
          text: 'quarterly plan',
          x: 100 / 1920,
          y: 540 / 1080,
          w: 100 / 1920,
          h: 20 / 1080,
          confidence: 1
        },
        { text: 'Edit', x: 20 / 1920, y: 545 / 1080, w: 40 / 1920, h: 20 / 1080, confidence: 1 },
        { text: 'Save', x: 10 / 1920, y: 1050 / 1080, w: 40 / 1920, h: 10 / 1080, confidence: 1 }
      ])
    })
    expect(buildSpatialOcrText(productionShaped)).toBe('- Edit | quarterly plan')
  })

  it('falls back for malformed or incomplete geometry without reintroducing chrome-only layouts', () => {
    expect(buildSpatialOcrText(frame({ ocrLinesJson: '{bad json' }))).toBe(
      'File Edit quarterly plan Save'
    )
    expect(
      buildSpatialOcrText(
        frame({
          ocrText: 'one two three four five six seven eight nine ten',
          ocrLinesJson: JSON.stringify([normalizedLine('one', 10, 200, 20, 10)])
        })
      )
    ).toBe('one two three four five six seven eight nine ten')
    expect(
      buildSpatialOcrText(
        frame({
          ocrText: 'alpha beta',
          ocrLinesJson: JSON.stringify([normalizedLine('alpha zeta', 10, 200, 80, 10)])
        })
      )
    ).toBe('alpha beta')
    expect(
      buildSpatialOcrText(
        frame({
          ocrText: 'File Save',
          ocrLinesJson: JSON.stringify([
            normalizedLine('File', 10, 20, 20, 10),
            normalizedLine('Save', 10, 1050, 40, 10)
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
        normalizedLine('File', 10, 20, 20, 10),
        normalizedLine('quarterly plans', 100, 200, 100, 20),
        normalizedLine('Edit', 20, 205, 40, 20),
        normalizedLine('Save', 10, 1050, 40, 10)
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
