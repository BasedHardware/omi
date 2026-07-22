import { useRef } from 'react'
import { cn } from '../../../lib/utils'
import { fractionToValue, snapToStep, valueToFraction } from './sliderMath'

/**
 * Settings-scoped continuous slider — a clean, native-feeling Windows (Fluent)
 * control, NOT a SwiftUI clone. Pointer-drag + full keyboard support over the
 * pure math in ./sliderMath.
 *
 * `ticks` renders small dots on the track (lit up to the current value) for a
 * future stepped consumer (e.g. voice speed); Font Size passes none.
 *
 * Motion charter: only transform/opacity animate (dev builds software-raster);
 * the thumb grows via `transition-transform`. Focus ring uses `outline` (its own
 * property, separate from the thumb's drop-shadow) shown on :focus-visible only —
 * never a `transition: all`.
 */
export function Slider(props: {
  value: number
  onChange: (next: number) => void
  min: number
  max: number
  step: number
  /** Filled-portion / lit-tick color. Defaults to the neutral brand accent. */
  tint?: string
  /** Optional leading/trailing adornments (e.g. the small/large "A" glyphs). */
  leftLabel?: React.ReactNode
  rightLabel?: React.ReactNode
  /** Required — the thumb is the focusable `role="slider"` element. */
  ariaLabel: string
  disabled?: boolean
  /** Values at which to draw step dots on the track. */
  ticks?: number[]
}): React.JSX.Element {
  const {
    value,
    onChange,
    min,
    max,
    step,
    tint = 'var(--accent)',
    leftLabel,
    rightLabel,
    ariaLabel,
    disabled,
    ticks
  } = props

  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  // Cached track geometry for the duration of a drag — the track can't move
  // mid-drag in a settings panel, so we measure once on pointerdown instead of on
  // every pointermove.
  const dragRect = useRef<DOMRect | null>(null)

  const fraction = valueToFraction(value, min, max)
  const pct = `${fraction * 100}%`

  const emitFromClientX = (clientX: number): void => {
    const rect = dragRect.current
    if (!rect || rect.width <= 0) return
    const next = fractionToValue((clientX - rect.left) / rect.width, min, max, step)
    if (next !== value) onChange(next)
  }

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (disabled || e.button !== 0) return
    dragging.current = true
    dragRect.current = e.currentTarget.getBoundingClientRect()
    e.currentTarget.setPointerCapture(e.pointerId)
    emitFromClientX(e.clientX)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (!dragging.current || disabled) return
    emitFromClientX(e.clientX)
  }
  const endDrag = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (!dragging.current) return
    dragging.current = false
    dragRect.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (disabled) return
    let next = value
    switch (e.key) {
      case 'ArrowLeft':
      case 'ArrowDown':
        next = value - step
        break
      case 'ArrowRight':
      case 'ArrowUp':
        next = value + step
        break
      case 'Home':
        next = min
        break
      case 'End':
        next = max
        break
      default:
        return
    }
    e.preventDefault()
    next = snapToStep(next, min, max, step)
    if (next !== value) onChange(next)
  }

  return (
    <div className={cn('flex items-center gap-3', disabled && 'opacity-40')}>
      {leftLabel != null && (
        <div className="shrink-0 select-none text-text-tertiary">{leftLabel}</div>
      )}
      <div
        ref={trackRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          'relative h-4 flex-1 touch-none select-none',
          disabled ? 'cursor-not-allowed' : 'cursor-pointer'
        )}
      >
        {/* Unfilled track */}
        <div
          className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full"
          style={{ background: 'var(--bg-quaternary)' }}
        />
        {/* Filled portion */}
        <div
          className="absolute left-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full"
          style={{ width: pct, background: tint }}
        />
        {/* Step dots (optional) */}
        {ticks?.map((t) => {
          const lit = t <= value
          return (
            <span
              key={t}
              className="pointer-events-none absolute top-1/2 h-1 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full"
              style={{
                left: `${valueToFraction(t, min, max) * 100}%`,
                background: lit ? tint : 'var(--text-tertiary)',
                opacity: lit ? 1 : 0.5
              }}
            />
          )
        })}
        {/* Thumb — the focusable slider element */}
        <div
          role="slider"
          tabIndex={disabled ? -1 : 0}
          aria-label={ariaLabel}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
          aria-disabled={disabled || undefined}
          onKeyDown={onKeyDown}
          className={cn(
            'absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white',
            'outline outline-2 outline-offset-2 outline-transparent transition-transform duration-150',
            'focus-visible:outline-white/60',
            !disabled && 'hover:scale-110 active:scale-110'
          )}
          style={{ left: pct, boxShadow: '0 1px 3px rgba(0,0,0,0.25)' }}
        />
      </div>
      {rightLabel != null && (
        <div className="shrink-0 select-none text-text-tertiary">{rightLabel}</div>
      )}
    </div>
  )
}
