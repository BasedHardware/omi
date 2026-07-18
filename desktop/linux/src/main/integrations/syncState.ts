// Per-source sync state (lastSyncAt + processed IDs) in userData JSON. Wraps the
// pure syncStateLogic so the merge/dedup/bound rules stay unit-tested.
import { app } from 'electron'
import { existsSync, readFileSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'
import { emptySourceState, recordProcessed, type SourceState } from './syncStateLogic'
import type { GoogleSource } from '../../shared/types'

type SyncFile = { gmail: SourceState; calendar: SourceState }

function file(): string {
  return join(app.getPath('userData'), 'google-sync.json')
}

function read(): SyncFile {
  try {
    if (existsSync(file())) {
      const raw = JSON.parse(readFileSync(file(), 'utf8')) as Partial<SyncFile>
      return {
        gmail: raw.gmail ?? emptySourceState(),
        calendar: raw.calendar ?? emptySourceState()
      }
    }
  } catch {
    /* fall through to empty */
  }
  return { gmail: emptySourceState(), calendar: emptySourceState() }
}

function write(state: SyncFile): void {
  writeFileSync(file(), JSON.stringify(state), 'utf8')
}

export function getSourceState(source: GoogleSource): SourceState {
  return read()[source]
}

export function markProcessed(source: GoogleSource, ids: string[]): void {
  const state = read()
  state[source] = recordProcessed(state[source], ids, Date.now())
  write(state)
}

/** Most recent successful sync across both sources (0 if never). */
export function lastSyncAt(): number {
  const s = read()
  return Math.max(s.gmail.lastSyncAt, s.calendar.lastSyncAt)
}

export function clearSyncState(): void {
  try {
    rmSync(file(), { force: true })
  } catch {
    /* best-effort */
  }
}
