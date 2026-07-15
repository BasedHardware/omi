import type { LucideIcon } from 'lucide-react'
import { Button } from '../../../ui/Button'
import { slugify } from '../../../../lib/kgTech'

// A single connector ROW in the Connections panel — the faithful port of macOS's
// AppsPage import/export rows: a 34px brand icon, a title + one-line description,
// and a right-aligned pill action, stacked in a hairline-divided list (no card
// borders, no status dots — Mac uses the button state + secondary text instead).
// Fitted to the Windows Hub tokens (home-*). An optional `children` body expands
// below the row for the flows that need more than a pill (paste box, previews).
//
// Icons follow Mac's brand marks: pass `iconNode` with a <ConnectorBrandMark> for
// the service's real logo, or a plain lucide `icon` (neutral) for generic rows.
// `onClick` makes the whole row a button (the marketplace link), so it doesn't
// re-declare this container's styling.

export function ConnectorRow(props: {
  icon?: LucideIcon
  iconNode?: React.ReactNode
  title: string
  /** One-line status/description under the title. */
  description: React.ReactNode
  /** Right-aligned pill action(s). Use <PillButton> for the white/neutral pills. */
  action?: React.ReactNode
  /** When set the whole row becomes a button (e.g. the App Marketplace link). */
  onClick?: () => void
  /** Optional expanded body below the row (ignored for the button variant). */
  children?: React.ReactNode
}): React.JSX.Element {
  const { icon: Icon, iconNode, title, description, action, onClick, children } = props
  const testid = `connector-${slugify(title)}`

  const inner = (
    <div className="flex items-center gap-3.5 py-3.5">
      <span
        className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[9px]"
        style={{ backgroundColor: 'rgb(255 255 255 / 0.05)' }}
      >
        {iconNode ??
          (Icon && <Icon className="h-[17px] w-[17px] text-home-secondary" strokeWidth={1.75} />)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[14px] font-semibold text-home-ink">{title}</div>
        {/* One line, clamped: a longer status/description must never make one row
            taller than its siblings (the Sticky Notes row used to wrap and stand
            proud of the list). */}
        <div className="mt-0.5 line-clamp-1 text-[12.5px] leading-snug text-home-muted">
          {description}
        </div>
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  )

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        data-testid={testid}
        className="w-full border-b border-home-hairline text-left transition-colors last:border-b-0 hover:bg-white/[0.03]"
      >
        {inner}
      </button>
    )
  }

  return (
    <div className="border-b border-home-hairline last:border-b-0" data-testid={testid}>
      {inner}
      {children && <div className="pb-4">{children}</div>}
    </div>
  )
}

// The row's pill action. `primary` = Mac's white "Connect" pill (white fill / dark
// ink); `neutral` = the connected-state "Sync now"/"Open" pill; `ghost` = a quiet
// "Disconnect". Built on the shared Button primitive, forced to a full pill radius.
export function PillButton({
  tone = 'primary',
  children,
  ...rest
}: {
  tone?: 'primary' | 'neutral' | 'ghost'
} & React.ButtonHTMLAttributes<HTMLButtonElement>): React.JSX.Element {
  const variant = tone === 'primary' ? 'primary' : tone === 'neutral' ? 'secondary' : 'ghost'
  return (
    <Button variant={variant} size="sm" className="rounded-full px-4" {...rest}>
      {children}
    </Button>
  )
}
