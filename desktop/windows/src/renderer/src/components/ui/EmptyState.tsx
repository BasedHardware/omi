import type { LucideIcon } from 'lucide-react'

export function EmptyState(props: {
  icon: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
}): React.JSX.Element {
  const Icon = props.icon
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="glass mb-5 flex h-16 w-16 items-center justify-center">
        <Icon className="h-7 w-7 text-white/50" strokeWidth={1.5} />
      </div>
      <p className="font-display text-xl font-semibold text-white/90">{props.title}</p>
      {props.description && (
        <p className="mt-2 max-w-sm text-sm leading-relaxed text-white/45">{props.description}</p>
      )}
      {props.action && <div className="mt-6">{props.action}</div>}
    </div>
  )
}
