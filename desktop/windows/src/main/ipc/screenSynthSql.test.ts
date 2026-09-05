import { DatabaseSync } from 'node:sqlite'
import { describe, expect, it } from 'vitest'
import { SCREEN_SYNTH_FRAMES_SQL, type ScreenSynthFrameRow } from './screenSynthSql'

describe('screen synthesis frame query', () => {
  it('returns only indexed frames in the requested range and keeps OCR geometry private', () => {
    const db = new DatabaseSync(':memory:')
    db.exec(`
      CREATE TABLE rewind_frames (
        ts INTEGER NOT NULL,
        app TEXT NOT NULL,
        window_title TEXT NOT NULL,
        process_name TEXT NOT NULL,
        ocr_text TEXT NOT NULL,
        ocr_lines_json TEXT,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        indexed INTEGER NOT NULL
      );
      CREATE INDEX idx_rewind_frames_ts ON rewind_frames(ts);
    `)
    const insert = db.prepare('INSERT INTO rewind_frames VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
    insert.run(99, 'Old', 'old', 'old.exe', 'old', null, 1920, 1080, 1)
    insert.run(100, 'Code', 'plan.md', 'code.exe', 'draft', '[{"text":"draft"}]', 1920, 1080, 1)
    insert.run(101, 'Code', 'plan.md', 'code.exe', '', null, 1920, 1080, 0)
    insert.run(102, 'Docs', 'API', 'browser.exe', '', null, 1920, 1080, 1)
    insert.run(103, 'New', 'new', 'new.exe', 'new', null, 1920, 1080, 1)

    const rows = db.prepare(SCREEN_SYNTH_FRAMES_SQL).all(100, 102) as ScreenSynthFrameRow[]

    expect(rows.map((row) => row.ts)).toEqual([100, 102])
    expect(rows[0]).toEqual({
      ts: 100,
      app: 'Code',
      windowTitle: 'plan.md',
      processName: 'code.exe',
      ocrText: 'draft',
      ocrLinesJson: '[{"text":"draft"}]',
      height: 1080
    })
    expect(Object.keys(rows[0])).not.toContain('imagePath')
    db.close()
  })
})
