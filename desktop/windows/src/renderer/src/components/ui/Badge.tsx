import { cn } from '../../lib/utils'

type BadgeTone = 'neutral' | 'success' | 'warning' | 'error' | 'info'
type BadgeSize = 'xs' | 'sm'

// Token-mapped tones — a tinted fill + a solid ink of the same status hue. The
// status keys (success/warning/error/info) resolve from the Tailwind palette so
// the alpha modifier can compute a real rgba tint.
const toneClasses: Record<BadgeTone, string> = {
  neutral: 'bg-white/10 text-white/70',
  success: 'bg-success/15 text-success',
  warning: 'bg-warning/15 text-warning',
  error: 'bg-error/15 text-error',
  info: 'bg-info/15 text-info'
}

const sizeClasses: Record<BadgeSize, string> = {
  xs: 'px-1.5 py-0.5 text-[10px]',
  sm: 'px-2 py-0.5 text-[11px]'
}

type BadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: BadgeTone
  size?: BadgeSize
}

// Small count/label pill — the going-forward primitive for the legacy
// `.badge`/`.badge-warning` globals.css utilities.
export function Badge({
  tone = 'neutral',
  size = 'sm',
  className,
  children,
  ...rest
}: BadgeProps): React.JSX.Element {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium leading-none',
        toneClasses[tone],
        sizeClasses[size],
        className
      )}
      {...rest}
    >
      {children}
    </span>
  )
}
