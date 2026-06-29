import type { OcrLine } from '../../shared/types'

const MAX_STORED_OCR_LINES = 200
const ROW_CLUSTER_THRESHOLD_PX = 10
const CHROME_EDGE_PX_AT_1080P = 40
const REFERENCE_SCREEN_HEIGHT = 1080

export type OcrLayoutRow = {
  top: number
  bottom: number
  left: number
  right: number
  text: string
  lines: OcrLine[]
}

type FrameSize = { width?: number; height?: number }
type ClusterOptions = { rowThresholdPx?: number }

function finiteNumber(value: number): boolean {
  return Number.isFinite(value)
}

function roundCoord(value: number): number {
  return Math.round(value)
}

export function normalizeOcrLines(lines: OcrLine[] | undefined): OcrLine[] {
  if (!Array.isArray(lines)) return []
  return lines
    .filter((line) => {
      const text = line.text?.trim()
      return (
        !!text &&
        finiteNumber(line.x) &&
        finiteNumber(line.y) &&
        finiteNumber(line.w) &&
        finiteNumber(line.h) &&
        line.w > 0 &&
        line.h > 0
      )
    })
    .slice(0, MAX_STORED_OCR_LINES)
    .map((line) => ({
      text: line.text.trim(),
      x: roundCoord(line.x),
      y: roundCoord(line.y),
      w: roundCoord(line.w),
      h: roundCoord(line.h),
      confidence: finiteNumber(line.confidence) ? line.confidence : 0
    }))
}

export function serializeOcrLinesForStorage(lines: OcrLine[] | undefined): string | null {
  const normalized = normalizeOcrLines(lines)
  return normalized.length ? JSON.stringify(normalized) : null
}

export function parseStoredOcrLines(json: string | null | undefined): OcrLine[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return normalizeOcrLines(Array.isArray(parsed) ? (parsed as OcrLine[]) : undefined)
  } catch {
    return []
  }
}

function sameRow(row: OcrLayoutRow, line: OcrLine, thresholdPx: number): boolean {
  return Math.abs(row.top - line.y) <= thresholdPx
}

function joinRowText(lines: OcrLine[]): string {
  const sorted = [...lines].sort((a, b) => a.x - b.x)
  let out = ''
  let previousRight = 0
  for (const line of sorted) {
    if (!out) {
      out = line.text
    } else {
      const gap = line.x - previousRight
      out += gap > Math.max(24, line.h * 2) ? ` | ${line.text}` : ` ${line.text}`
    }
    previousRight = Math.max(previousRight, line.x + line.w)
  }
  return out
}

export function clusterOcrRows(lines: OcrLine[], options: ClusterOptions = {}): OcrLayoutRow[] {
  const thresholdPx = options.rowThresholdPx ?? ROW_CLUSTER_THRESHOLD_PX
  const sorted = normalizeOcrLines(lines).sort((a, b) => a.y - b.y || a.x - b.x)
  const rows: OcrLayoutRow[] = []

  for (const line of sorted) {
    const current = rows[rows.length - 1]
    if (!current || !sameRow(current, line, thresholdPx)) {
      rows.push({
        top: line.y,
        bottom: line.y + line.h,
        left: line.x,
        right: line.x + line.w,
        text: line.text,
        lines: [line]
      })
      continue
    }

    current.lines.push(line)
    current.top = Math.min(current.top, line.y)
    current.bottom = Math.max(current.bottom, line.y + line.h)
    current.left = Math.min(current.left, line.x)
    current.right = Math.max(current.right, line.x + line.w)
    current.text = joinRowText(current.lines)
  }

  return rows.map((row) => ({
    ...row,
    lines: [...row.lines].sort((a, b) => a.x - b.x),
    text: joinRowText(row.lines)
  }))
}

function chromeEdgePx(size: FrameSize): number {
  if (!size.height || size.height <= 0) return CHROME_EDGE_PX_AT_1080P
  return Math.round((size.height / REFERENCE_SCREEN_HEIGHT) * CHROME_EDGE_PX_AT_1080P)
}

export function filterScreenChromeLines(lines: OcrLine[], size: FrameSize = {}): OcrLine[] {
  const normalized = normalizeOcrLines(lines)
  const topCutoff = chromeEdgePx(size)
  const bottomCutoff = size.height && size.height > 0 ? size.height - topCutoff : null
  return normalized.filter((line) => {
    if (line.y < topCutoff) return false
    if (bottomCutoff != null && line.y > bottomCutoff) return false
    return true
  })
}

function pct(value: number, total: number | undefined): number | null {
  if (!total || total <= 0) return null
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)))
}

function rowLabel(row: OcrLayoutRow, size: FrameSize): string {
  const top = pct(row.top, size.height)
  const left = pct(row.left, size.width)
  if (top == null && left == null) return ''
  if (top == null) return `left ${left}%`
  if (left == null) return `top ${top}%`
  return `top ${top}%, left ${left}%`
}

export function serializeOcrLayoutMarkdown(lines: OcrLine[], size: FrameSize = {}): string {
  return clusterOcrRows(filterScreenChromeLines(lines, size))
    .map((row) => {
      const label = rowLabel(row, size)
      return label ? `- ${label}: ${row.text}` : `- ${row.text}`
    })
    .join('\n')
}

export function buildOcrContextText(
  ocrText: string,
  ocrLinesJson: string | null | undefined,
  size: FrameSize = {}
): string {
  const layout = serializeOcrLayoutMarkdown(parseStoredOcrLines(ocrLinesJson), size).trim()
  return layout || ocrText.trim()
}
