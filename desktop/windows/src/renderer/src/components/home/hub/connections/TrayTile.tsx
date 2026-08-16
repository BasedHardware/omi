import { ChevronRight, Plus } from 'lucide-react'
import { ConnectorBrandMark, type ConnectorBrand } from './ConnectorBrandMark'
import { slugify } from '../../../../lib/kgTech'

// A single tile in the Connections tray — the faithful port of macOS's
// HomeAIChoiceButton (DashboardPage.swift). A 48px rounded row: a brand icon in a
// small rounded square, a bold label, an optional right-aligned muted "Connected",
// and a trailing chevron. The "+ More" variant renders a bare plus (no icon square)
// exactly as Mac does for its systemImage rows. Fitted to the Windows Hub tokens.

export function TrayTile(props: {
  title: string
  /** A brand mark in the leading icon square; omit for the "+ More" plus variant. */
  brand?: ConnectorBrand
  /** Renders the bare leading plus instead of a brand square (the "More" rows). */
  plus?: boolean
  connected?: boolean
  /** Override the derived testid — the two "+ More" tiles slugify identically. */
  testId?: string
  onClick: () => void
}): React.JSX.Element {
  const { title, brand, plus, connected, testId, onClick } = props
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId ?? `tray-tile-${slugify(title)}`}
      className="flex h-12 w-full items-center gap-2.5 rounded-[15px] border border-home-hairline bg-home-tile px-3.5 text-left transition-colors hover:bg-white/[0.05]"
    >
      {plus ? (
        <span className="flex h-7 w-7 shrink-0 items-center justify-center">
          <Plus className="h-[15px] w-[15px] text-home-ink" strokeWidth={2.25} />
        </span>
      ) : (
        // A uniform brand chip — dark rounded square + hairline, the mark inset ~18%
        // so even full-bleed logos (Hermes) show the chip frame. Ports macOS's
        // ConnectorBrandIcon so every mark reads as one treatment, not mixed glyphs
        // and colored squares.
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] border border-white/[0.06] p-[5px]"
          style={{ backgroundColor: 'rgb(255 255 255 / 0.05)' }}
        >
          {brand && <ConnectorBrandMark brand={brand} />}
        </span>
      )}
      <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-home-ink">
        {title}
      </span>
      {connected && (
        <span className="shrink-0 text-[11px] font-medium text-home-faint">Connected</span>
      )}
      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-home-faint" strokeWidth={2.25} />
    </button>
  )
}
