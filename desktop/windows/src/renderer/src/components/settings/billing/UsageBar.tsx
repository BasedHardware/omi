import { cn } from '../../../lib/utils'

/**
 * A thin usage meter. Neutral white fill by default; shifts to an amber warning
 * tint at/over the threshold. Deliberately NOT purple — Mac's bar is purple, but
 * purple is off-brand here (INV-UI-1). `fraction` is 0–1.
 */
export function UsageBar(props: { fraction: number; warning?: boolean }): React.JSX.Element {
  const pct = Math.max(0, Math.min(1, props.fraction)) * 100
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
      <div
        className={cn(
          'h-full rounded-full transition-all duration-500',
          props.warning ? 'bg-amber-400' : 'bg-white/70'
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
