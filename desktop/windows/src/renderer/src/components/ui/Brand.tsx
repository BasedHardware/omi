import { cn } from '../../lib/utils'

// Cortex brand marks — pure text/CSS, no image asset. The wordmark uses the
// Oxanium display font; the small mark is a rounded "C" used as the assistant
// avatar in chat.

export function CortexWordmark(props: { className?: string }): React.JSX.Element {
  return (
    <span
      className={cn('font-display font-semibold tracking-tight text-text-primary', props.className)}
      style={{ letterSpacing: '0.02em' }}
    >
      Cortex
    </span>
  )
}

export function CortexMark(props: { className?: string }): React.JSX.Element {
  return (
    <span
      className={cn('font-display font-bold leading-none', props.className)}
      style={{ color: 'var(--accent)' }}
    >
      C
    </span>
  )
}
