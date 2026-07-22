import { Slot } from '@radix-ui/react-slot'
import { cn } from '../../lib/utils'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md'

// Flat, Fluent-native button surfaces built on PR#1 tokens — NOT SwiftUI chrome.
// primary = white accent fill with dark ink; secondary = raised neutral; ghost =
// text-only with a faint hover wash; danger = the shared error red.
const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-[var(--accent)] text-[var(--accent-contrast)] hover:bg-white/90',
  secondary: 'bg-[var(--bg-tertiary)] text-white hover:bg-[var(--bg-quaternary)]',
  ghost: 'bg-transparent text-white hover:bg-white/5',
  danger: 'bg-[var(--error)] text-white hover:bg-[var(--error)]/90'
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 gap-1.5 px-3 text-[13px]',
  md: 'h-10 gap-2 px-4 text-sm'
}

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  // Render the child element as the button (Radix Slot) — for links/router
  // targets styled as buttons. Loading spinner is suppressed in this mode since
  // Slot requires a single child.
  asChild?: boolean
}

// A compact inline spinner sized for the button rail (the shared <Spinner> is
// fixed at 40px — too large to sit inside a control).
function ButtonSpinner(): React.JSX.Element {
  return (
    <span
      className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70"
      aria-hidden
    />
  )
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  asChild = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps): React.JSX.Element {
  const classes = cn(
    'focus-ring inline-flex select-none items-center justify-center rounded-[var(--radius-control)] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40',
    variantClasses[variant],
    sizeClasses[size],
    className
  )

  if (asChild) {
    return (
      <Slot className={classes} {...rest}>
        {children}
      </Slot>
    )
  }

  return (
    <button
      type="button"
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <ButtonSpinner />}
      {children}
    </button>
  )
}
