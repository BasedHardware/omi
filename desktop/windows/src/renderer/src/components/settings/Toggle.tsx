import { cn } from '../../lib/utils'

// macOS-style switch. Controlled: `on` + `onChange`. Used for the right-aligned
// control in SettingRow.
export function Toggle(props: {
  on: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  label?: string
}): React.JSX.Element {
  const { on, onChange, disabled, label } = props
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={cn(
        'relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200',
        on ? 'bg-[color:var(--accent)]' : 'bg-white/15',
        disabled && 'cursor-not-allowed opacity-40'
      )}
    >
      <span
        className={cn(
          'absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all duration-200',
          on ? 'left-[1.125rem]' : 'left-0.5'
        )}
      />
    </button>
  )
}
