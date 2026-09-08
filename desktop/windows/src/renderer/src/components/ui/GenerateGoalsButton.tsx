import { Sparkles, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'

// Shared "generate goals with AI" button: dark surface background with the
// accent-colored Sparkles icon + label. Used both on the Goals tab and on the
// Home Goals widget (when there are no goals yet).
export function GenerateGoalsButton(props: {
  onClick: () => void
  loading?: boolean
  label?: string
  className?: string
}): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.loading}
      className={cn(
        'inline-flex items-center gap-2 rounded-xl border border-white/10 bg-[color:var(--surface)] px-3.5 py-2 text-sm font-medium text-[color:var(--accent)] transition-colors hover:border-white/20 disabled:opacity-60',
        props.className
      )}
    >
      {props.loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Sparkles className="h-4 w-4" />
      )}
      {props.label ?? 'Generate goals with AI'}
    </button>
  )
}
