import { app } from 'electron'
import { join } from 'path'
import { mkdirSync } from 'fs'

/** Root dir for rewind JPEGs: <userData>/rewind */
export function rewindRoot(): string {
  return join(app.getPath('userData'), 'rewind')
}

/** Per-day subdir (YYYY-MM-DD), created if missing. */
export function rewindDayDir(tsMs: number): string {
  const d = new Date(tsMs)
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate()
  ).padStart(2, '0')}`
  const dir = join(rewindRoot(), day)
  mkdirSync(dir, { recursive: true })
  return dir
}

/** Absolute path for a frame's JPEG: <root>/<day>/<ts>.jpg */
export function rewindFramePath(tsMs: number): string {
  return join(rewindDayDir(tsMs), `${tsMs}.jpg`)
}
