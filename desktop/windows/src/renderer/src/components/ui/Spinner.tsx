import { cn } from '../../lib/utils'

export function Spinner(props: { className?: string; label?: string }): React.JSX.Element {
  return (
    <div className={cn('flex flex-col items-center gap-4', props.className)} role="status">
      <div
        className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-white/70"
        aria-hidden
      />
      {props.label && <p className="text-sm text-white/45">{props.label}</p>}
    </div>
  )
}
