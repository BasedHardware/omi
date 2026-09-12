// Renderer-facing surface for the Activity spine's screen data.
//
// Reads only, so it is not gated to the main window: this returns the same
// capture the Rewind page already shows. Two channels rather than one, because
// the two answers have very different sizes - the day list is a handful of
// numbers and is needed immediately, while a day projection carries up to a few
// hundred frames and is only worth fetching for days actually on screen.

import { ipcMain } from 'electron'
import { spineScreenDay, spineScreenDays } from './db'
import type { ScreenDayProjection } from '../spine/screenIndex'

/** Most days offered to the spine at once. The stream pages further back by
 *  conversation and memory, which are cheap; screen days are not. */
export const MAX_SCREEN_DAYS = 30

const emptyDay = (dayId: number): ScreenDayProjection => ({
  dayId,
  total: 0,
  hourCounts: new Array<number>(24).fill(0),
  sampled: []
})

export function listScreenDays(limit?: unknown): number[] {
  const bounded =
    typeof limit === 'number' && Number.isFinite(limit)
      ? Math.max(1, Math.min(Math.floor(limit), MAX_SCREEN_DAYS))
      : MAX_SCREEN_DAYS
  try {
    return spineScreenDays(bounded)
  } catch (e) {
    // A timeline that cannot read screen capture still has conversations,
    // memories and tasks to show; failing the whole page over this would be a
    // worse answer than a timeline with no screen rows in it.
    console.error('[spine] screen day list failed', e)
    return []
  }
}

export function readScreenDay(dayId: unknown): ScreenDayProjection | null {
  if (typeof dayId !== 'number' || !Number.isFinite(dayId)) return null
  const day = Math.floor(dayId)
  try {
    return spineScreenDay(day)
  } catch (e) {
    console.error('[spine] screen day projection failed', e)
    // A zeroed day, not null: the caller asked and got an answer, so the rail
    // shows 0 rather than sitting on "counting" forever.
    return emptyDay(day)
  }
}

export function registerSpineHandlers(): void {
  ipcMain.handle('omi-spine:screen-days', (_e, limit?: unknown) => listScreenDays(limit))
  ipcMain.handle('omi-spine:screen-day', (_e, dayId: unknown) => readScreenDay(dayId))
}
