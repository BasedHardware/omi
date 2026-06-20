export function StatusTile({
  label,
  value,
  tone = 'neutral'
}: {
  label: string
  value: string
  tone?: 'good' | 'warn' | 'neutral'
}): React.JSX.Element {
  const dot = tone === 'good' ? 'bg-emerald-400' : tone === 'warn' ? 'bg-amber-300' : 'bg-white/30'
  return (
    <div className="min-w-0 rounded-lg bg-white/[0.04] px-3 py-2">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-text-tertiary">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-1 truncate text-sm text-text-secondary">{value}</div>
    </div>
  )
}
