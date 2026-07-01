import { memo, useEffect, useRef, useState } from 'react'
import type { RewindFrame, RewindSearchGroup } from '../../../../shared/types'

const timeLabel = (ts: number): string =>
  new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

const groupRangeLabel = (startTs: number, endTs: number): string => {
  const start = new Date(startTs).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
  if (startTs === endTs) return start
  return `${start} - ${timeLabel(endTs)}`
}

const ResultImage = memo(function ResultImage({
  frame,
  className
}: {
  frame: RewindFrame
  className: string
}): React.JSX.Element {
  const root = useRef<HTMLSpanElement | null>(null)
  const [visible, setVisible] = useState(false)
  const [image, setImage] = useState<{ path: string; src: string } | null>(null)
  const src = image?.path === frame.imagePath ? image.src : null

  useEffect(() => {
    if (visible) return
    const node = root.current
    if (!node || typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        setVisible(true)
        observer.disconnect()
      },
      { rootMargin: '240px' }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [visible])

  useEffect(() => {
    if (!visible) return
    let alive = true
    void window.omi
      .rewindFrameImage(frame.imagePath)
      .then((dataUrl) => {
        if (alive) setImage({ path: frame.imagePath, src: dataUrl })
      })
      .catch(() => {
        if (alive) setImage(null)
      })
    return () => {
      alive = false
    }
  }, [frame.imagePath, visible])

  return (
    <span ref={root} className={`block overflow-hidden rounded bg-black/40 ${className}`}>
      {src ? <img src={src} alt="" className="h-full w-full object-cover" /> : null}
    </span>
  )
})

export function SearchResultsFilmstrip({
  groups,
  onJump,
  query,
  searching,
  onOpenSettings
}: {
  groups: RewindSearchGroup[]
  query: string
  searching: boolean
  onJump: (ts: number) => void
  onOpenSettings?: () => void
}): React.JSX.Element {
  if (searching) {
    return (
      <div className="flex h-full items-center justify-center rounded bg-white/5 text-sm text-white/45">
        Searching OCR...
      </div>
    )
  }

  if (groups.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 rounded bg-white/5 px-4 text-center text-sm text-white/45">
        <span>No Rewind OCR matches for &quot;{query}&quot;.</span>
        {onOpenSettings && (
          <button onClick={onOpenSettings} className="btn-ghost">
            Check Rewind settings
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="flex h-full gap-3 overflow-x-auto pb-1">
      {groups.map((g) => (
        <button
          key={g.id}
          onClick={() => onJump(g.representative.ts)}
          className="flex w-80 shrink-0 gap-3 rounded bg-white/5 p-3 text-left hover:bg-white/10"
        >
          <ResultImage frame={g.representative} className="h-24 w-36 shrink-0" />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="truncate text-xs font-medium text-white/80">
              {g.app || 'Unknown app'}
            </div>
            <div className="truncate text-[11px] text-white/45">
              {g.windowTitle || groupRangeLabel(g.startTs, g.endTs)}
            </div>
            <div className="text-[11px] text-white/45">{groupRangeLabel(g.startTs, g.endTs)}</div>
            <div className="line-clamp-2 min-h-8 text-xs leading-4 text-white/80">
              {g.matchSnippet}
            </div>
            <div className="mt-auto flex h-9 gap-1 overflow-hidden">
              {g.frames.slice(0, 5).map((frame) => (
                <ResultImage key={frame.ts} frame={frame} className="h-9 w-12 shrink-0" />
              ))}
              {g.frames.length > 5 && (
                <span className="flex h-9 w-12 shrink-0 items-center justify-center rounded bg-white/10 text-[11px] text-white/60">
                  +{g.frames.length - 5}
                </span>
              )}
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}
