import { cn } from '../../lib/utils'

type ToggleProps = {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  // Visible/associated label text; also used as the accessible name. When both
  // are omitted, `ariaLabel` (else "Toggle") keeps the switch from being unnamed.
  label?: string
  ariaLabel?: string
}

// Fluent pill switch (mirrors the existing Windows Sidebar/Settings toggle), NOT
// an Apple green toggle. Track 40×22; OFF = faint white track + translucent
// thumb, ON = white accent track + dark thumb. The thumb slides on transform
// only (cheap, GPU-composited). A <button> gives free Space/Enter activation.
export function Toggle({
  checked,
  onChange,
  disabled,
  label,
  ariaLabel
}: ToggleProps): React.JSX.Element {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label ?? ariaLabel ?? 'Toggle'}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'focus-ring relative inline-flex h-[22px] w-10 shrink-0 items-center rounded-full transition-colors duration-200',
        checked ? 'bg-[var(--accent)]' : 'bg-white/15',
        disabled && 'cursor-not-allowed opacity-40'
      )}
    >
      <span
        aria-hidden
        className={cn(
          'pointer-events-none inline-block h-[18px] w-[18px] rounded-full transition-transform duration-200 will-change-transform',
          checked ? 'translate-x-5 bg-[var(--accent-contrast)]' : 'translate-x-0.5 bg-white/50'
        )}
      />
    </button>
  )
}
