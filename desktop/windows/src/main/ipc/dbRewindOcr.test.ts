import { describe, it, expect, vi } from 'vitest'
import type { RewindFrame } from '../../shared/types'

const dbState = vi.hoisted(() => ({
  inserted: null as Omit<RewindFrame, 'id'> | null,
  update: null as [string, string | null, number] | null
}))

vi.mock('electron', () => ({
  app: {
    getPath: () => 'test-user-data'
  }
}))

vi.mock('better-sqlite3', () => ({
  default: class FakeDatabase {
    pragma(): null {
      return null
    }
    exec(): this {
      return this
    }
    prepare(sql: string): {
      all: (...args: unknown[]) => unknown[]
      get: (...args: unknown[]) => unknown
      run: (...args: unknown[]) => { lastInsertRowid?: number; changes: number }
      columns: () => { name: string }[]
    } {
      return {
        all: () => {
          if (sql.startsWith('PRAGMA table_info')) {
            return [
              { name: 'kind' },
              { name: 'messages' },
              { name: 'title' },
              { name: 'summary' },
              { name: 'id' },
              { name: 'target_path' },
              { name: 'ocr_lines_json' }
            ]
          }
          if (sql.includes('FROM rewind_frames WHERE ts BETWEEN')) {
            return [
              {
                id: 7,
                ...dbState.inserted,
                ocrText: dbState.update?.[0] ?? '',
                ocrLinesJson: dbState.update?.[1] ?? null,
                indexed: 1
              }
            ]
          }
          return []
        },
        get: () => undefined,
        run: (...args: unknown[]) => {
          if (sql.includes('INSERT INTO rewind_frames')) {
            dbState.inserted = args[0] as Omit<RewindFrame, 'id'>
            return { lastInsertRowid: 7, changes: 1 }
          }
          if (sql.includes('UPDATE rewind_frames SET ocr_text')) {
            dbState.update = args as [string, string | null, number]
          }
          return { changes: 1 }
        },
        columns: () => []
      }
    }
  }
}))

function frame(over: Partial<RewindFrame> = {}): Omit<RewindFrame, 'id'> {
  return {
    ts: 1000,
    app: 'Code',
    windowTitle: 'plan.md',
    processName: 'Code.exe',
    ocrText: '',
    imagePath: 'frame.jpg',
    width: 800,
    height: 600,
    indexed: 0,
    ...over
  }
}

describe('rewind OCR db wiring', () => {
  it('persists OCR text and layout JSON on rewind frames', async () => {
    dbState.inserted = null
    dbState.update = null
    vi.resetModules()
    const { insertRewindFrame, listRewindFrames, setRewindFrameOcr } = await import('./db')

    const id = insertRewindFrame(frame())
    setRewindFrameOcr(id, 'Hello world', [
      { text: 'Hello', x: 10, y: 10, w: 40, h: 12, confidence: 0.99 },
      { text: 'world', x: 56, y: 10, w: 40, h: 12, confidence: 0.98 }
    ])

    const rows = listRewindFrames(0, 2000)
    expect(rows).toHaveLength(1)
    expect(rows[0].ocrText).toBe('Hello world')
    expect(rows[0].indexed).toBe(1)
    expect(JSON.parse(rows[0].ocrLinesJson ?? '[]')).toEqual([
      { text: 'Hello', x: 10, y: 10, w: 40, h: 12, confidence: 0.99 },
      { text: 'world', x: 56, y: 10, w: 40, h: 12, confidence: 0.98 }
    ])
  })
})
