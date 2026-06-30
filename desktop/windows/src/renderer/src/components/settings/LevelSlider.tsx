import { useCallback, useRef } from 'react'

/**
 * Discrete "ruler" slider: small marker … ticks + draggable thumb … large marker.
 * Snaps to a fixed set of levels (no in-between values). Drag, click-to-jump, and
 * arrow keys all move by whole levels. Used for the font-size controls (small A …
 * large A) and the capture-resolution control (small … large marker).
 */
export function LevelSlider(props: {
  /** Current scale value (must be one of `levels`, or the nearest is highlighted). */
  value: number
  /** Ordered scale values, smallest → largest. */
  levels: number[]
  onChange: (scale: number) => void
  ariaLabel: string
  /** Left ("smallest") and right ("largest") end markers. Default: small/large "A". */
  minLabel?: React.ReactNode
  maxLabel?: React.ReactNode
  /** Spoken value for screen readers. Default: a percentage (assumes a 0-1 scale). */
  valueText?: (v: number) => string
}): React.JSX.Element {
  const { value, levels, onChange, ariaLabel, minLabel, maxLabel, valueText } = props
  const trackRef = useRef<HTMLDivElement>(null)
  const max = levels.length - 1

  // Index of the active level (nearest, if `value` isn't exactly a level).
  let index = levels.indexOf(value)
  if (index < 0) {
    index = levels.reduce(
      (best, lv, i) => (Math.abs(lv - value) < Math.abs(levels[best] - value) ? i : best),
      0
    )
  }

  const setFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const frac = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
      const next = levels[Math.round(frac * max)]
      if (next !== value) onChange(next)
    },
    [levels, max, onChange, value]
  )

  const onPointerDown = (e: React.PointerEvent): void => {
    e.currentTarget.setPointerCapture(e.pointerId)
    setFromClientX(e.clientX)
  }
  const onPointerMove = (e: React.PointerEvent): void => {
    if (e.buttons === 0) return // only while dragging
    setFromClientX(e.clientX)
  }
  const onKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault()
      onChange(levels[Math.max(0, index - 1)])
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault()
      onChange(levels[Math.min(max, index + 1)])
    } else if (e.key === 'Home') {
      e.preventDefault()
      onChange(levels[0])
    } else if (e.key === 'End') {
      e.preventDefault()
      onChange(levels[max])
    }
  }

  const thumbPct = (index / max) * 100

  return (
    <div className="flex select-none items-center gap-3">
      <span className="flex w-3 items-center justify-center text-[13px] leading-none text-text-tertiary">
        {minLabel ?? 'A'}
      </span>
      <div
        ref={trackRef}
        role="slider"
        tabIndex={0}
        aria-label={ariaLabel}
        aria-valuemin={Math.round(levels[0] * 100)}
        aria-valuemax={Math.round(levels[max] * 100)}
        aria-valuenow={Math.round(value * 100)}
        aria-valuetext={valueText ? valueText(value) : `${Math.round(value * 100)}%`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onKeyDown={onKeyDown}
        className="relative h-8 flex-1 cursor-pointer rounded-md outline-none focus-visible:ring-1 focus-visible:ring-white/25"
      >
        {/* Baseline */}
        <div className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-white/15" />
        {/* One tick per selectable level — no decorative in-between marks. */}
        {levels.map((_, i) => (
          <span
            key={i}
            className="absolute top-1/2 w-px -translate-x-1/2 -translate-y-1/2 bg-white/35"
            style={{ left: `${(i / max) * 100}%`, height: 12 }}
          />
        ))}
        {/* Thumb */}
        <div
          className="absolute top-1/2 h-5 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-[0_1px_4px_rgba(0,0,0,0.4)]"
          style={{ left: `${thumbPct}%` }}
        />
      </div>
      <span className="flex w-4 items-center justify-center text-xl leading-none text-text-tertiary">
        {maxLabel ?? 'A'}
      </span>
    </div>
  )
}
