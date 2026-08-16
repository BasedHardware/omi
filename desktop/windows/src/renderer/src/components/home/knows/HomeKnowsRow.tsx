import { useState } from 'react'
import { Circle, Lightbulb, MessageSquare, ArrowUpRight, X, Clock } from 'lucide-react'
import { cn } from '../../../lib/utils'
import type { KnowsRow } from '../../../lib/intelligence/knowsComposer'
import type { FeedbackReason } from '../../../lib/intelligence/wireTypes'

// One knows-list row (mac parity: HomeKnowsRowView, DashboardPage.swift ~2400).
// Task rows dismiss immediately; insight rows open the optional-reason popover
// first, and closing it without choosing still dismisses (reason null, mac
// parity); question rows have no dismiss at all — they render the open chevron
// instead of the close button.

const DISMISS_REASONS: { label: string; reason: FeedbackReason }[] = [
  { label: 'Already handled', reason: 'already_handled' },
  { label: 'Not mine', reason: 'not_mine' },
  { label: 'Not useful', reason: 'not_useful' }
]

export function HomeKnowsRow({
  row,
  onOpen,
  onDismiss,
  onLater
}: {
  row: KnowsRow
  onOpen: () => void
  /** Absent for question rows (they cannot be dismissed). Insight rows receive
   *  the chosen reason or null when the popover closes without one. */
  onDismiss?: (reason: FeedbackReason | null) => void
  /** Insight rows only: push the recommendation back 24h. */
  onLater?: () => void
}): React.JSX.Element {
  const [reasonOpen, setReasonOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  const Icon = row.kind === 'task' ? Circle : row.kind === 'insight' ? Lightbulb : MessageSquare

  const dismissClicked = (): void => {
    if (!onDismiss) return
    if (row.kind === 'insight') {
      setReasonOpen(true)
      return
    }
    onDismiss(null)
  }

  const chooseReason = (reason: FeedbackReason | null): void => {
    setReasonOpen(false)
    onDismiss?.(reason)
  }

  const openContextMenu = (e: React.MouseEvent): void => {
    // Mac parity: the row's context menu carries Later and Dismiss. Question
    // rows have neither, so the default menu is fine there.
    if (!onDismiss && !onLater) return
    e.preventDefault()
    setMenuOpen(true)
  }

  return (
    <div
      className="group relative w-full shrink-0"
      data-testid={`home-knows-${row.id}`}
      onContextMenu={openContextMenu}
    >
      <div
        className={cn(
          'flex h-[46px] w-full items-center gap-2.5 rounded-[13px]',
          'border border-home-hairline bg-home-tile/[0.55] px-4',
          'transition-colors duration-150 hover:bg-home-tileHover'
        )}
      >
        <button
          type="button"
          onClick={onOpen}
          className="focus-ring flex min-w-0 flex-1 items-center gap-2.5 text-left"
        >
          <Icon className="h-[12px] w-[12px] shrink-0 text-home-muted" strokeWidth={2.25} />
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-home-secondary group-hover:text-home-ink">
            {row.text}
          </span>
        </button>
        {onDismiss ? (
          <span className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
            {onLater && (
              <button
                type="button"
                onClick={onLater}
                aria-label="Later"
                title="Later"
                className="focus-ring rounded p-1 text-home-faint hover:text-home-secondary"
              >
                <Clock className="h-3 w-3" strokeWidth={2.5} />
              </button>
            )}
            <button
              type="button"
              onClick={dismissClicked}
              aria-label="Dismiss"
              title="Dismiss"
              className="focus-ring rounded p-1 text-home-faint hover:text-home-secondary"
            >
              <X className="h-3 w-3" strokeWidth={2.5} />
            </button>
          </span>
        ) : (
          <ArrowUpRight className="h-2.5 w-2.5 shrink-0 text-home-faint" strokeWidth={2.5} />
        )}
      </div>

      {menuOpen && (
        <>
          <button
            type="button"
            aria-label="Close menu"
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setMenuOpen(false)}
          />
          <div
            className="absolute right-0 top-[48px] z-50 w-[130px] rounded-[10px] border border-home-hairline bg-home-tile p-1 shadow-lg"
            data-testid="knows-context-menu"
          >
            {onLater && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false)
                  onLater()
                }}
                className="focus-ring block w-full rounded px-2 py-1.5 text-left text-[12px] text-home-secondary hover:bg-home-tileHover hover:text-home-ink"
              >
                Later
              </button>
            )}
            {onDismiss && (
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false)
                  dismissClicked()
                }}
                className="focus-ring block w-full rounded px-2 py-1.5 text-left text-[12px] text-home-secondary hover:bg-home-tileHover hover:text-home-ink"
              >
                Dismiss
              </button>
            )}
          </div>
        </>
      )}

      {reasonOpen && (
        <>
          {/* Click-away closes without a reason — which still dismisses. */}
          <button
            type="button"
            aria-label="Dismiss without a reason"
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => chooseReason(null)}
          />
          <div
            className="absolute right-0 top-[48px] z-50 w-[210px] rounded-[10px] border border-home-hairline bg-home-tile p-2 shadow-lg"
            data-testid="knows-dismiss-reasons"
          >
            <p className="px-1 pb-1 text-[11px] font-semibold text-home-muted">Optional reason</p>
            {DISMISS_REASONS.map(({ label, reason }) => (
              <button
                key={reason}
                type="button"
                onClick={() => chooseReason(reason)}
                className="focus-ring block w-full rounded px-2 py-1.5 text-left text-[12px] text-home-secondary hover:bg-home-tileHover hover:text-home-ink"
              >
                {label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
