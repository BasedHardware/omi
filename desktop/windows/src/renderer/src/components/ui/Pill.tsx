import type { LucideIcon } from 'lucide-react'
import { cn } from '../../lib/utils'

type PillProps = {
  children: React.ReactNode
  // A leading status dot: `true` uses the current text color; a string sets a
  // custom color (e.g. a token or hex).
  dot?: boolean | string
  icon?: LucideIcon
  onClick?: () => void
  className?: string
  title?: string
}

// Capsule status/label chip on the raised token surface. Distinct from Badge:
// Pill is for status/interactive affordances (bigger tap target, hover, optional
// onClick), Badge is a compact count/label. Renders a <button> when interactive.
export function Pill({
  children,
  dot,
  icon: Icon,
  onClick,
  className,
  title
}: PillProps): React.JSX.Element {
  const base =
    'inline-flex items-center gap-1.5 rounded-full bg-[var(--bg-tertiary)] px-3 py-1 text-[13px] font-medium text-white/80'

  const inner = (
    <>
      {dot && (
        <span
          aria-hidden
          className="h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ background: typeof dot === 'string' ? dot : 'currentColor' }}
        />
      )}
      {Icon && <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={2} aria-hidden />}
      <span className="truncate">{children}</span>
    </>
  )

  if (onClick) {
    return (
      <button
        type="button"
        title={title}
        onClick={onClick}
        className={cn(
          base,
          'focus-ring transition-colors hover:bg-[var(--bg-quaternary)]',
          className
        )}
      >
        {inner}
      </button>
    )
  }

  return (
    <span title={title} className={cn(base, className)}>
      {inner}
    </span>
  )
}
