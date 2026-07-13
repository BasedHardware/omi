import type { LucideIcon } from 'lucide-react'
import { cn } from '../../../lib/utils'

export type IconTone = 'neutral' | 'green' | 'amber' | 'yellow'

const ICON_TONE: Record<IconTone, string> = {
  neutral: 'text-white/70',
  green: 'text-emerald-400',
  amber: 'text-amber-400',
  yellow: 'text-yellow-300'
  // Mac accents Architect/CTAs purple; per INV-UI-1 nothing here is purple.
}

/**
 * Shared shell for the billing cards — a dark glass card (Windows `surface-card`
 * idiom) with the Mac composition: a leading tinted icon, a title + subtitle
 * text column, an optional trailing control, and an optional expanded body.
 */
export function BillingCard(props: {
  icon: LucideIcon
  iconTone?: IconTone
  title: React.ReactNode
  subtitle?: React.ReactNode
  trailing?: React.ReactNode
  children?: React.ReactNode
  className?: string
}): React.JSX.Element {
  const { icon: Icon, iconTone = 'neutral', title, subtitle, trailing, children, className } = props
  return (
    <div className={cn('surface-card p-5', className)}>
      <div className="flex items-start gap-3.5">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/[0.06]">
          <Icon className={cn('h-[18px] w-[18px]', ICON_TONE[iconTone])} strokeWidth={1.9} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold leading-tight text-text-primary">{title}</div>
          {subtitle ? <div className="mt-1 text-sm text-text-tertiary">{subtitle}</div> : null}
        </div>
        {trailing ? <div className="ml-2 shrink-0">{trailing}</div> : null}
      </div>
      {children ? <div className="mt-4">{children}</div> : null}
    </div>
  )
}
