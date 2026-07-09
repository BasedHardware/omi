import { mkdtemp, rm } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import Database from 'better-sqlite3'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RewindFrame } from '../../shared/types'

let userDataPath = ''

vi.mock('electron', () => ({
  app: {
    getPath: () => userDataPath
  }
}))

async function freshDbPath(): Promise<string> {
  userDataPath = await mkdtemp(join(tmpdir(), 'omi-rewind-db-'))
  process.env.OMI_DB_PATH = join(userDataPath, 'omi.db')
  vi.resetModules()
  return process.env.OMI_DB_PATH
}

function frame(over: Partial<Omit<RewindFrame, 'id'>>): Omit<RewindFrame, 'id'> {
  return {
    ts: 0,
    app: 'Code.exe',
    windowTitle: 'index.ts',
    processName: 'Code',
    ocrText: 'hello world',
    imagePath: join(userDataPath, 'frame.jpg'),
    width: 1280,
    height: 720,
    indexed: 1,
    ...over
  }
}

describe('rewind DB search', () => {
  beforeEach(async () => {
    await freshDbPath()
  })

  afterEach(async () => {
    const db = await import('./db')
    db.closeDatabase()
    delete process.env.OMI_DB_PATH
    delete process.env.OMI_REWIND_DISABLE_FTS
    vi.resetModules()
    if (userDataPath) await rm(userDataPath, { recursive: true, force: true })
    userDataPath = ''
  })

  it('finds OCR content, app name, and window title with recent results first', async () => {
    const db = await import('./db')
    const old = db.insertRewindFrame(
      frame({ ts: 1_000, app: 'Slack.exe', ocrText: 'quarterly roadmap review' })
    )
    const mid = db.insertRewindFrame(
      frame({ ts: 2_000, app: 'Firefox Developer Edition', ocrText: 'blank page' })
    )
    const recent = db.insertRewindFrame(
      frame({ ts: 3_000, windowTitle: 'Pull Request 42 - Omi', ocrText: '' })
    )

    expect(db.searchRewindFrames('quarterly roadmap').map((f) => f.id)).toEqual([old])
    expect(db.searchRewindFrames('firefox').map((f) => f.id)).toEqual([mid])
    expect(db.searchRewindFrames('pull request').map((f) => f.id)).toEqual([recent])

    db.insertRewindFrame(frame({ ts: 4_000, ocrText: 'quarterly roadmap follow-up' }))
    expect(db.searchRewindFrames('quarterly roadmap').map((f) => f.ts)).toEqual([4_000, 1_000])
  })

  it('keeps LIKE fallback search working when FTS is disabled', async () => {
    process.env.OMI_REWIND_DISABLE_FTS = '1'
    vi.resetModules()
    const db = await import('./db')
    const id = db.insertRewindFrame(
      frame({ ts: 1_000, app: 'Notepad.exe', windowTitle: 'Meeting notes', ocrText: '' })
    )

    expect(db.searchRewindFrames('notepad').map((f) => f.id)).toEqual([id])
    expect(db.searchRewindFrames('meeting notes').map((f) => f.id)).toEqual([id])
  })

  it('migrates old rewind_frames tables with missing searchable metadata columns', async () => {
    const path = process.env.OMI_DB_PATH!
    const old = new Database(path)
    old.exec(`
      CREATE TABLE rewind_frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        image_path TEXT NOT NULL
      );
      INSERT INTO rewind_frames (ts, image_path) VALUES (123, '${join(userDataPath, 'old.jpg').replace(/'/g, "''")}');
    `)
    old.close()

    const db = await import('./db')
    const rows = db.listRewindFrames(0, 200)

    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({
      ts: 123,
      app: '',
      windowTitle: '',
      processName: '',
      ocrText: '',
      width: 0,
      height: 0,
      indexed: 0
    })
  })

  it('deleteAllRewindFrames removes base rows and FTS OCR entries', async () => {
    const db = await import('./db')
    db.insertRewindFrame(frame({ ts: 1_000, ocrText: 'confidential payroll numbers' }))
    db.insertRewindFrame(frame({ ts: 2_000, app: 'Slack.exe', windowTitle: 'DM with legal' }))
    expect(db.searchRewindFrames('payroll')).toHaveLength(1)

    const deleted = db.deleteAllRewindFrames()

    expect(deleted).toBe(2)
    expect(db.listRewindFrames(0, 10_000)).toEqual([])
    expect(db.searchRewindFrames('payroll')).toEqual([])
    db.closeDatabase()

    // Inspect the raw file: the FTS index must hold zero rows, so no OCR,
    // window-title, or app text survives the "delete everything" action.
    const raw = new Database(process.env.OMI_DB_PATH!)
    const ftsRows = raw.prepare('SELECT COUNT(*) AS n FROM rewind_frames_fts').get() as {
      n: number
    }
    const ftsMatches = raw
      .prepare('SELECT COUNT(*) AS n FROM rewind_frames_fts WHERE rewind_frames_fts MATCH ?')
      .get('payroll OR legal OR Slack') as { n: number }
    raw.close()
    expect(ftsRows.n).toBe(0)
    expect(ftsMatches.n).toBe(0)
  })

  it('summarizes Rewind diagnostic status', async () => {
    const db = await import('./db')

    expect(db.rewindStatusStats()).toEqual({
      latestFrameTs: null,
      oldestFrameTs: null,
      totalFrameCount: 0,
      indexedFrameCount: 0,
      ocrBacklogCount: 0
    })

    db.insertRewindFrame(frame({ ts: 1_000, indexed: 0 }))
    db.insertRewindFrame(frame({ ts: 3_000, indexed: 1 }))
    db.insertRewindFrame(frame({ ts: 2_000, indexed: 0 }))

    expect(db.rewindStatusStats()).toEqual({
      latestFrameTs: 3_000,
      oldestFrameTs: 1_000,
      totalFrameCount: 3,
      indexedFrameCount: 1,
      ocrBacklogCount: 2
    })
  })
})
