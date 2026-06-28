import type { RewindFrame, RewindSearchGroup } from '../../shared/types'

/** Temporal window for clustering consecutive frames (matches macOS 30s). */
export const GROUP_WINDOW_MS = 30_000

function snippet(text: string, query: string): string {
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx < 0) return text.slice(0, 80)
  const start = Math.max(0, idx - 30)
  return (start > 0 ? '…' : '') + text.slice(start, idx + query.length + 30).trim() + '…'
}

/**
 * Cluster a flat frame list into groups: consecutive frames within
 * GROUP_WINDOW_MS of the group's start that share the same app + window title.
 * Input order is irrelevant (sorted ascending internally); output is newest group first.
 */
export function groupFrames(frames: RewindFrame[], query: string): RewindSearchGroup[] {
  const sorted = [...frames].sort((a, b) => a.ts - b.ts)
  const groups: RewindSearchGroup[] = []
  let current: RewindFrame[] = []

  const flush = (): void => {
    if (current.length === 0) return
    const first = current[0]
    const last = current[current.length - 1]
    const rep = current.find((f) => f.ocrText.toLowerCase().includes(query.toLowerCase())) ?? last
    groups.push({
      id: `${first.app}-${first.ts}`,
      app: first.app,
      windowTitle: first.windowTitle,
      startTs: first.ts,
      endTs: last.ts,
      frames: [...current],
      representative: rep,
      matchSnippet: snippet(rep.ocrText, query)
    })
    current = []
  }

  for (const f of sorted) {
    if (current.length === 0) {
      current.push(f)
      continue
    }
    const first = current[0]
    const prev = current[current.length - 1]
    const sameContext = prev.app === f.app && prev.windowTitle === f.windowTitle
    const withinWindow = f.ts - first.ts <= GROUP_WINDOW_MS
    if (sameContext && withinWindow) current.push(f)
    else {
      flush()
      current.push(f)
    }
  }
  flush()
  return groups.sort((a, b) => b.startTs - a.startTs)
}
