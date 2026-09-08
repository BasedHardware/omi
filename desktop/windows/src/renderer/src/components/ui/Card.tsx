import { cn } from '../../lib/utils'

type CardPadding = 'none' | 'sm' | 'md' | 'lg'

const paddingClasses: Record<CardPadding, string> = {
  none: '',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-6'
}

type CardProps = React.HTMLAttributes<HTMLDivElement> & {
  padding?: CardPadding
  // Adds a hover lift (border + fill step) for cards that act as buttons/links.
  interactive?: boolean
}

// Flat Fluent surface on the PR#1 token ramp — a raised panel with a hairline
// stroke and a soft shadow. No Apple card chrome (no inner highlight, no glass).
export function Card({
  padding = 'md',
  interactive = false,
  className,
  children,
  ...rest
}: CardProps): React.JSX.Element {
  return (
    <div
      className={cn(
        'rounded-[var(--radius-card)] border border-white/[0.08] bg-[var(--bg-secondary)] shadow-[0_1px_3px_rgba(0,0,0,0.3)]',
        paddingClasses[padding],
        interactive &&
          'cursor-pointer transition-colors hover:border-white/[0.16] hover:bg-[var(--bg-tertiary)]',
        className
      )}
      {...rest}
    >
      {children}
    </div>
  )
}
