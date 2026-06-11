import { memo, useEffect, useMemo, useRef, useState } from 'react'
import type { RewindFrame } from '../../../../shared/types'
import { REWIND_ACTIVITY_GAP_MS } from '../../../../shared/timelineGeometry'
import {
  buildStripItems,
  activeStripIndex,
  stripItemTs,
  gapWidthPx,
  formatGapDuration
} from '../../lib/rewindStrip'
import { useElementWidth } from '../../hooks/useElementWidth'

// Gap spacers are sized by duration so blank time is proportional.
const GAP_PX_PER_MS = 0.001
const GAP_MIN_PX = 36
const GAP_MAX_PX = 4000

const Thumb = memo(function Thumb({
  frame,
  active,
  onSeek,
  root
}: {
  frame: RewindFrame
  active: boolean
  onSeek: (ts: number) => void
  root: React.RefObject<HTMLDivElement | null>
}): React.JSX.Element {
  const [src, setSrc] = useState<string | null>(null)
  const elRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const el = elRef.current
    if (!el) return
    let alive = true
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect()
          void window.omi.rewindFrameImage(frame.imagePath).then((d) => {
            if (alive) setSrc(d)
          })
        }
      },
      { root: root.current, rootMargin: '400px' }
    )
    io.observe(el)
    return () => {
      alive = false
      io.disconnect()
    }
  }, [frame.imagePath, root])

  const time = new Date(frame.ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return (
    <button ref={elRef} onClick={() => onSeek(frame.ts)} className="flex w-28 shrink-0 flex-col gap-1 text-left">
      <span
        className={`h-16 w-28 overflow-hidden rounded border ${active ? 'border-[color:var(--accent)] ring-1 ring-[color:var(--accent)]' : 'border-white/10'}`}
      >
        {src && <img src={src} alt="" className="h-full w-full object-cover" />}
      </span>
      <span className="leading-tight">
        <span className="block text-[11px] text-white/75">{time}</span>
        <span className="block truncate text-[10px] text-white/40">{frame.app || 'Unknown app'}</span>
      </span>
    </button>
  )
})

function GapSpacer({
  from,
  to,
  active,
  onClick
}: {
  from: number
  to: number
  active: boolean
  onClick: () => void
}): React.JSX.Element {
  const width = gapWidthPx(to - from, GAP_PX_PER_MS, GAP_MIN_PX, GAP_MAX_PX)
  return (
    <button
      onClick={onClick}
      style={{ width }}
      className={`flex h-16 shrink-0 flex-col items-center justify-center gap-0.5 self-start rounded border border-dashed text-[10px] ${
        active ? 'border-[color:var(--accent)] text-[color:var(--accent)]' : 'border-white/10 text-white/30'
      }`}
    >
      <span className="uppercase tracking-wide">no activity</span>
      <span>{formatGapDuration(to - from)}</span>
    </button>
  )
}

export function RewindThumbnailStrip({
  frames,
  cursorTs,
  onSeek
}: {
  frames: RewindFrame[]
  cursorTs: number
  onSeek: (ts: number) => void
}): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const programmaticRef = useRef(false)
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Measured so layout/scroll re-runs once the real width is known (fixes the
  // "nothing shows until I click" first-paint measurement gap).
  const width = useElementWidth(containerRef)

  const items = useMemo(() => buildStripItems(frames, REWIND_ACTIVITY_GAP_MS), [frames])
  const activeIdx = activeStripIndex(items, cursorTs)

  // Cursor → scroll: keep the active item in view (skip if already roughly
  // centered so the user's own scrolling isn't fought).
  useEffect(() => {
    const el = containerRef.current
    if (!el || activeIdx < 0 || width === 0) return
    const child = el.children[activeIdx] as HTMLElement | undefined
    if (!child) return
    const contCenter = el.scrollLeft + el.clientWidth / 2
    const childCenter = child.offsetLeft + child.offsetWidth / 2
    if (Math.abs(childCenter - contCenter) < child.offsetWidth / 2 + el.clientWidth / 4) return
    programmaticRef.current = true
    child.scrollIntoView({ inline: 'center', block: 'nearest' })
    const t = setTimeout(() => {
      programmaticRef.current = false
    }, 200)
    return () => clearTimeout(t)
  }, [activeIdx, width])

  // Scroll → cursor: move the shared cursor to whatever item is centred.
  const handleScroll = (): void => {
    if (programmaticRef.current) return
    if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current)
    scrollTimerRef.current = setTimeout(() => {
      const el = containerRef.current
      if (!el) return
      const center = el.scrollLeft + el.clientWidth / 2
      let bestIdx = -1
      let bestDist = Infinity
      for (let i = 0; i < el.children.length; i++) {
        const c = el.children[i] as HTMLElement
        const cCenter = c.offsetLeft + c.offsetWidth / 2
        const d = Math.abs(cCenter - center)
        if (d < bestDist) {
          bestDist = d
          bestIdx = i
        }
      }
      if (bestIdx >= 0 && items[bestIdx]) onSeek(stripItemTs(items[bestIdx]))
    }, 120)
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      // A vertical mouse wheel doesn't scroll an overflow-x container, so translate
      // wheel delta into horizontal scroll (the strip is horizontal).
      onWheel={(e) => {
        const el = containerRef.current
        if (el && e.deltaY !== 0) el.scrollLeft += e.deltaY
      }}
      className="flex items-start gap-2 overflow-x-auto py-2"
    >
      {items.map((item, i) =>
        item.kind === 'frame' ? (
          <Thumb
            key={`f-${item.frame.ts}`}
            frame={item.frame}
            active={i === activeIdx}
            onSeek={onSeek}
            root={containerRef}
          />
        ) : (
          <GapSpacer
            key={`g-${item.from}`}
            from={item.from}
            to={item.to}
            active={i === activeIdx}
            onClick={() => onSeek(stripItemTs(item))}
          />
        )
      )}
    </div>
  )
}
