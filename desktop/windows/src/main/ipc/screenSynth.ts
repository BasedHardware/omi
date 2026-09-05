// src/main/ipc/screenSynth.ts
import { ipcMain } from 'electron'
import { listScreenSynthFrames } from './db'
import {
  getScreenSynthState,
  updateScreenSynthState,
  advanceWatermark,
  recordRun
} from '../screenSynth/state'
import type { OcrLine, ScreenFrameLite, ScreenSynthState, ScreenSynthRun } from '../../shared/types'
import type { ScreenSynthFrameRow } from './screenSynthSql'

const ROW_CLUSTER_THRESHOLD_PX = 10
const CHROME_EDGE_PX_AT_1080P = 40
const REFERENCE_FRAME_HEIGHT = 1080
const NEAR_DUPLICATE_THRESHOLD = 0.92

type SpatialRow = { anchorY: number; lines: OcrLine[] }

function normalizedLine(value: unknown): OcrLine | null {
  if (!value || typeof value !== 'object') return null
  const line = value as Record<string, unknown>
  const text = typeof line.text === 'string' ? line.text.trim().replace(/\s+/g, ' ') : ''
  const finite = (field: string): number | null => {
    const candidate = line[field]
    return typeof candidate === 'number' && Number.isFinite(candidate) ? candidate : null
  }
  const x = finite('x')
  const y = finite('y')
  const w = finite('w')
  const h = finite('h')
  if (!text || x == null || y == null || w == null || h == null || w <= 0 || h <= 0) {
    return null
  }
  return {
    text,
    x,
    y,
    w,
    h,
    confidence: finite('confidence') ?? 0
  }
}

function parseStoredOcrLines(raw: string | null): OcrLine[] | null {
  if (!raw) return null
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed.map(normalizedLine).filter((line): line is OcrLine => line !== null)
  } catch {
    return null
  }
}

function coverageTokens(text: string): string[] {
  return text.trim().split(/\s+/).filter(Boolean).sort()
}

function hasCompleteTextCoverage(lineText: string, plainText: string): boolean {
  const lineTokens = coverageTokens(lineText)
  const plainTokens = coverageTokens(plainText)
  return (
    lineTokens.length === plainTokens.length &&
    lineTokens.every((token, index) => token === plainTokens[index])
  )
}

function chromeEdgePx(height: number): number {
  const effectiveHeight = Number.isFinite(height) && height > 0 ? height : REFERENCE_FRAME_HEIGHT
  return (effectiveHeight / REFERENCE_FRAME_HEIGHT) * CHROME_EDGE_PX_AT_1080P
}

function clusterRows(lines: OcrLine[]): SpatialRow[] {
  const rows: SpatialRow[] = []
  const sorted = [...lines].sort((a, b) => a.y - b.y || a.x - b.x)
  for (const line of sorted) {
    const current = rows[rows.length - 1]
    if (!current || Math.abs(current.anchorY - line.y) >= ROW_CLUSTER_THRESHOLD_PX) {
      rows.push({ anchorY: line.y, lines: [line] })
    } else {
      current.lines.push(line)
    }
  }
  return rows
}

/** Build layout-aware OCR while preserving plain text when stored geometry is incomplete. */
export function buildSpatialOcrText(frame: ScreenSynthFrameRow): string {
  const plainText = frame.ocrText.trim()
  const lines = parseStoredOcrLines(frame.ocrLinesJson)
  if (!lines) return plainText

  const lineText = lines.map((line) => line.text).join(' ')
  if (plainText && !hasCompleteTextCoverage(lineText, plainText)) {
    return plainText
  }

  const edge = chromeEdgePx(frame.height)
  const effectiveHeight =
    Number.isFinite(frame.height) && frame.height > 0 ? frame.height : REFERENCE_FRAME_HEIGHT
  const contentLines = lines.filter((line) => line.y >= edge && line.y <= effectiveHeight - edge)

  return clusterRows(contentLines)
    .map(
      (row) =>
        `- ${[...row.lines]
          .sort((a, b) => a.x - b.x)
          .map((line) => line.text)
          .join(' | ')}`
    )
    .join('\n')
}

type DistanceBand = { start: number; values: number[] }

function bandValue(band: DistanceBand, index: number, outside: number): number {
  const offset = index - band.start
  return offset >= 0 && offset < band.values.length ? band.values[offset] : outside
}

function hasAlignedEditScriptWithin(left: string, right: string, maxDistance: number): boolean {
  const overlap = Math.min(left.length, right.length)
  const lengthDelta = Math.abs(left.length - right.length)
  const withinFromOffsets = (leftOffset: number, rightOffset: number): boolean => {
    let edits = lengthDelta
    for (let i = 0; i < overlap && edits <= maxDistance; i++) {
      if (left.charCodeAt(leftOffset + i) !== right.charCodeAt(rightOffset + i)) edits++
    }
    return edits <= maxDistance
  }

  if (withinFromOffsets(0, 0)) return true
  if (lengthDelta === 0) return false
  return withinFromOffsets(left.length - overlap, right.length - overlap)
}

function characterCountLowerBoundExceeds(
  left: string,
  right: string,
  maxDistance: number
): boolean {
  const counts = new Map<number, number>()
  for (let i = 0; i < left.length; i++) {
    const code = left.charCodeAt(i)
    counts.set(code, (counts.get(code) ?? 0) + 1)
  }
  for (let i = 0; i < right.length; i++) {
    const code = right.charCodeAt(i)
    counts.set(code, (counts.get(code) ?? 0) - 1)
  }
  let imbalance = 0
  for (const count of counts.values()) imbalance += Math.abs(count)
  return Math.ceil(imbalance / 2) > maxDistance
}

// Only distances at or below maxDistance matter. Keep that diagonal band instead
// of allocating and evaluating the full Levenshtein matrix.
function isWithinLevenshteinDistance(left: string, right: string, maxDistance: number): boolean {
  let prefixLength = 0
  const sharedLength = Math.min(left.length, right.length)
  while (
    prefixLength < sharedLength &&
    left.charCodeAt(prefixLength) === right.charCodeAt(prefixLength)
  ) {
    prefixLength++
  }

  let leftEnd = left.length
  let rightEnd = right.length
  while (
    leftEnd > prefixLength &&
    rightEnd > prefixLength &&
    left.charCodeAt(leftEnd - 1) === right.charCodeAt(rightEnd - 1)
  ) {
    leftEnd--
    rightEnd--
  }

  const trimmedLeft = left.slice(prefixLength, leftEnd)
  const trimmedRight = right.slice(prefixLength, rightEnd)
  if (Math.abs(trimmedLeft.length - trimmedRight.length) > maxDistance) return false
  if (Math.max(trimmedLeft.length, trimmedRight.length) <= maxDistance) return true
  if (hasAlignedEditScriptWithin(trimmedLeft, trimmedRight, maxDistance)) return true
  if (characterCountLowerBoundExceeds(trimmedLeft, trimmedRight, maxDistance)) return false

  const outside = maxDistance + 1
  let previous: DistanceBand = {
    start: 0,
    values: Array.from({ length: Math.min(trimmedRight.length, maxDistance) + 1 }, (_, i) => i)
  }

  for (let i = 1; i <= trimmedLeft.length; i++) {
    const start = Math.max(0, i - maxDistance)
    const end = Math.min(trimmedRight.length, i + maxDistance)
    const values = Array<number>(end - start + 1).fill(outside)
    const current: DistanceBand = { start, values }

    for (let j = start; j <= end; j++) {
      const offset = j - start
      if (j === 0) {
        values[offset] = i
        continue
      }
      const deletion = bandValue(previous, j, outside) + 1
      const insertion = (offset > 0 ? values[offset - 1] : outside) + 1
      const substitution =
        bandValue(previous, j - 1, outside) +
        (trimmedLeft.charCodeAt(i - 1) === trimmedRight.charCodeAt(j - 1) ? 0 : 1)
      values[offset] = Math.min(deletion, insertion, substitution)
    }
    previous = current
  }

  return bandValue(previous, trimmedRight.length, outside) <= maxDistance
}

function normalizeForSimilarity(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim()
}

export function isNearDuplicateScreenText(previous: string, next: string): boolean {
  const left = normalizeForSimilarity(previous)
  const right = normalizeForSimilarity(next)
  if (!left || !right) return false
  if (left === right) return true

  const maxLength = Math.max(left.length, right.length)
  const minLength = Math.min(left.length, right.length)
  if (minLength / maxLength <= NEAR_DUPLICATE_THRESHOLD) return false

  // Similarity must EXCEED 92%, so an exact 8% edit distance is not a duplicate.
  const maxDistance = Math.ceil(maxLength * (1 - NEAR_DUPLICATE_THRESHOLD)) - 1
  return isWithinLevenshteinDistance(left, right, maxDistance)
}

function sameContext(previous: ScreenFrameLite, next: ScreenFrameLite): boolean {
  return (
    previous.app === next.app &&
    previous.windowTitle === next.windowTitle &&
    previous.processName === next.processName
  )
}

export function prepareScreenSynthFrames(frames: ScreenSynthFrameRow[]): ScreenFrameLite[] {
  const prepared: ScreenFrameLite[] = []
  let previousMeaningful: ScreenFrameLite | null = null

  for (const frame of frames) {
    const next: ScreenFrameLite = {
      ts: frame.ts,
      app: frame.app,
      windowTitle: frame.windowTitle,
      processName: frame.processName,
      ocrText: buildSpatialOcrText(frame)
    }
    const duplicate =
      previousMeaningful !== null &&
      sameContext(previousMeaningful, next) &&
      isNearDuplicateScreenText(previousMeaningful.ocrText, next.ocrText)

    // Keep a zero-text timestamp marker so the renderer still advances its watermark
    // past duplicate tail frames; grouping already ignores blank OCR.
    prepared.push(duplicate ? { ...next, ocrText: '' } : next)
    if (!duplicate) previousMeaningful = next
  }

  return prepared
}

export function registerScreenSynthHandlers(): void {
  // Frames since the watermark, stripped to the fields synthesis needs (no image bytes).
  ipcMain.handle('screenSynth:framesSince', async (): Promise<ScreenFrameLite[]> => {
    const { watermarkTs } = getScreenSynthState()
    // +1 so we never re-emit the exact watermark frame.
    return prepareScreenSynthFrames(listScreenSynthFrames(watermarkTs + 1, Date.now()))
  })
  ipcMain.handle('screenSynth:getState', async () => getScreenSynthState())
  ipcMain.handle('screenSynth:setState', async (_e, patch: Partial<ScreenSynthState>) =>
    updateScreenSynthState(patch)
  )
  ipcMain.handle('screenSynth:advanceWatermark', async (_e, ts: number) => {
    if (typeof ts === 'number' && ts > 0) advanceWatermark(ts)
  })
  ipcMain.handle('screenSynth:recordRun', async (_e, run: ScreenSynthRun) =>
    recordRun(run.lastRunAt, run.lastCount)
  )
}
