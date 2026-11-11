import { memo, useEffect, useRef, useState } from 'react'
import { Images, Sparkles } from 'lucide-react'
import type { RewindSearchGroup } from '../../../../shared/types'
import { parseWindowTitle } from '../../lib/windowTitle'
import { highlightTerms } from '../../lib/rewindOverlay'
import { highlightSegments } from '../../lib/rewindHighlight'

// macOS parity: search results are a vertical list of grouped hits
// (RewindPage.fullScreenResultsView) — representative thumbnail, app + window, the
// group's time range, a context snippet with the match highlighted, and a
// "N screenshots" badge for multi-frame groups. Selecting one drills into its
// mini-timeline (the parent handles that + loads the hit's day).

const THUMB_W = 120
const THUMB_H = 80

/** A group's time span, e.g. "Jul 12 · 3:04–3:06 PM" (or a single time for a
 *  one-frame / instantaneous group). */
function timeRange(startTs: number, endTs: number): string {
  const d = new Date(startTs)
  const date = d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  const t = (ms: number): string =>
    new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return startTs === endTs ? `${date} · ${t(startTs)}` : `${date} · ${t(startTs)}–${t(endTs)}`
}

const ResultThumb = memo(function ResultThumb({
  imagePath
}: {
  imagePath: string
}): React.JSX.Element {
  const [src, setSrc] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let alive = true
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect()
          void window.omi.rewindFrameImage(imagePath).then((d) => {
            if (alive) setSrc(d)
          })
        }
      },
      { rootMargin: '300px' }
    )
    io.observe(el)
    return () => {
      alive = false
      io.disconnect()
    }
  }, [imagePath])
  return (
    <div
      ref={ref}
      style={{ width: THUMB_W, height: THUMB_H }}
      className="shrink-0 overflow-hidden rounded border border-white/10 bg-black/40"
    >
      {src && <img src={src} alt="" className="h-full w-full object-cover" />}
    </div>
  )
})

function Snippet({ text, terms }: { text: string; terms: string[] }): React.JSX.Element {
  const segs = highlightSegments(text, terms)
  return (
    <p className="line-clamp-2 text-sm text-white/70">
      {segs.map((s, i) =>
        s.match ? (
          <mark key={i} className="bg-transparent font-semibold text-white">
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        )
      )}
    </p>
  )
}

export function SearchResultsFilmstrip({
  groups,
  query,
  onSelect,
  loading = false
}: {
  groups: RewindSearchGroup[]
  query: string
  onSelect: (group: RewindSearchGroup) => void
  /** True while the keyword round-trip is still in flight (shows the searching state). */
  loading?: boolean
}): React.JSX.Element {
  if (groups.length === 0) {
    return (
      <div className="py-10 text-center">
        <p className="text-sm text-white/60">{loading ? 'Searching…' : 'No results found'}</p>
        {!loading && <p className="mt-1 text-xs text-white/35">Try a different search term</p>}
      </div>
    )
  }
  const terms = highlightTerms(query)
  return (
    <div className="flex flex-col gap-2">
      {groups.map((g) => {
        const { app, title } = parseWindowTitle(g.windowTitle, g.app || 'Unknown app')
        return (
          <button
            key={g.id}
            data-testid="rewind-result"
            onClick={() => onSelect(g)}
            className="flex items-start gap-3 rounded-control border border-line bg-white/[0.04] p-2.5 text-left transition-colors hover:border-line-strong hover:bg-white/[0.08]"
          >
            <ResultThumb imagePath={g.representative.imagePath} />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <div className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className="truncate text-sm font-medium text-white/90">{app}</span>
                  {g.matchedSemantically && (
                    // Neutral "related" chip — this hit came from semantic recall, not
                    // a literal keyword match. Mac renders no purple here, so neither do we.
                    <span
                      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-white/15 px-1.5 py-0.5 text-[10px] text-white/55"
                      title="Matched by meaning, not an exact keyword"
                    >
                      <Sparkles className="h-2.5 w-2.5" />
                      Related
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-white/45">
                  {timeRange(g.startTs, g.endTs)}
                </span>
              </div>
              {title && <span className="truncate text-xs text-white/45">{title}</span>}
              <Snippet text={g.matchSnippet} terms={terms} />
              {g.frames.length > 1 && (
                <span className="mt-0.5 inline-flex w-fit items-center gap-1 rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-white/50">
                  <Images className="h-3 w-3" />
                  {g.frames.length} screenshots
                </span>
              )}
            </div>
          </button>
        )
      })}
    </div>
  )
}
