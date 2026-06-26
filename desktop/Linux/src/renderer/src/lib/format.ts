export function timeAgo(iso?: string): string {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const s = Math.max(0, (Date.now() - then) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`
  return new Date(iso).toLocaleDateString()
}

export function clockTime(iso?: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function segmentClock(seconds?: number): string {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Human conversation duration ("45s", "12m", "1h 5m"), mirrors ServerConversation.formattedDuration. */
export function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds) || seconds < 0) return ''
  const total = Math.floor(seconds)
  if (total < 60) return `${total}s`
  const m = Math.floor(total / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem ? `${h}h ${rem}m` : `${h}h`
}

/** Duration in seconds between started_at/finished_at (fallback created_at), if derivable. */
export function conversationDurationSeconds(conv: {
  created_at?: string
  started_at?: string
  finished_at?: string
  transcript_segments?: { end?: number; start?: number }[]
}): number | undefined {
  const startIso = conv.started_at ?? conv.created_at
  if (startIso && conv.finished_at) {
    const start = new Date(startIso).getTime()
    const end = new Date(conv.finished_at).getTime()
    if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
      const secs = (end - start) / 1000
      if (secs >= 1) return secs
    }
  }
  // Fall back to the span covered by the transcript segments.
  const segs = conv.transcript_segments
  if (segs && segs.length > 0) {
    let max = 0
    for (const s of segs) {
      const e = s.end ?? s.start
      if (e !== undefined && e > max) max = e
    }
    if (max >= 1) return max
  }
  return undefined
}

/** Elapsed mm:ss / h:mm:ss for a live recording counter. */
export function elapsedClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Speaker bubble color rotation from OmiColors.speakerColors. */
export const SPEAKER_COLORS = ['#2D3748', '#1E3A5F', '#2D4A3E', '#4A3728', '#3D2E4A', '#4A3A2D']

export function speakerColor(index: number | undefined, isUser: boolean | undefined): string {
  if (isUser) return '#43389F'
  return SPEAKER_COLORS[(index ?? 0) % SPEAKER_COLORS.length]
}

export function greeting(name?: string): string {
  const h = new Date().getHours()
  const part = h < 5 ? 'Good night' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
  return name ? `${part}, ${name}` : part
}
