import { useNavigate } from 'react-router-dom'
import { LayoutGrid, ArrowRight } from 'lucide-react'
import { registerHubConnectContent, type HubConnectSlotProps } from '../hubConnectSlot'
import { CalendarConnector } from './CalendarConnector'
import { GmailConnector } from './GmailConnector'
import { StickyNotesConnector } from './StickyNotesConnector'
import { PasteImportConnector } from './PasteImportConnector'
import { ExportsConnector } from './ExportsConnector'

// The Connections home — the content registered into the Hub's Connect stage (see
// hubConnectSlot.ts). It is the Windows-native port of macOS's AppsPage Imports/
// Exports hub: divider-separated connector rows under serif section headers, fitted
// to the Hub tokens, plus a link out to the full App Marketplace.
//
// IMPORTS pull external data INTO Omi's memory; EXPORTS push Omi's memory OUT. All
// connect/sync/import logic is shared with Settings via the lib/* services each row
// imports — this panel adds no business logic, only Hub-native presentation.
//
// ORDER — Mac's connector order is a STATIC curated array (ImportConnector.all:
// calendar, email, local-files, apple-notes, x, chatgpt, claude), not derived from
// state/metrics; the rendered list follows it in declaration order. Windows drops
// Local Files (it lives in Settings → Advanced / file indexing) and maps Apple
// Notes → Sticky Notes. X/Twitter lands in the follow-up connector PR, in its Mac
// slot (after Sticky Notes, before ChatGPT).
//
// SLOT CONTRACT: mount at 100%/100%, own the internal scroll (the Hub panel is
// overflow-hidden), never set an outer fixed size. See hubConnectSlot.ts.

function SectionHeader({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <h2 className="mb-1 font-serif text-[17px] font-medium text-home-secondary">{children}</h2>
}

export function ConnectionsPanel({ onDismiss }: HubConnectSlotProps): React.JSX.Element {
  const navigate = useNavigate()

  const openApps = (): void => {
    onDismiss()
    navigate('/apps')
  }

  return (
    <div className="flex h-full w-full flex-col" data-testid="connections-panel">
      <div className="shrink-0 px-6 pt-6">
        <h1 className="font-display text-[22px] font-bold lowercase leading-none text-home-ink">
          connections
        </h1>
        <p className="mt-1.5 text-[13px] text-home-muted">
          Bring your data into Omi, and send your memories where you work.
        </p>
      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto px-6 pb-6">
        <div className="mx-auto flex w-full max-w-[760px] flex-col gap-7">
          <section>
            <SectionHeader>Imports</SectionHeader>
            <div className="flex flex-col">
              <CalendarConnector />
              <GmailConnector />
              <StickyNotesConnector />
              {/* X/Twitter row lands here in the follow-up connector PR. */}
              <PasteImportConnector source="chatgpt" />
              <PasteImportConnector source="claude" />
            </div>
          </section>

          <section>
            <SectionHeader>Exports</SectionHeader>
            <div className="flex flex-col">
              <ExportsConnector />
            </div>
          </section>

          <button
            onClick={openApps}
            className="hover:bg-home-tileHover group flex items-center gap-3.5 rounded-section px-4 py-3.5 text-left transition-colors"
            style={{ backgroundColor: 'var(--home-tile)' }}
            data-testid="connections-apps-link"
          >
            <span
              className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[9px]"
              style={{ backgroundColor: 'rgb(255 255 255 / 0.05)' }}
            >
              <LayoutGrid className="h-[17px] w-[17px] text-home-secondary" strokeWidth={1.75} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[14px] font-semibold text-home-ink">
                Browse the App Marketplace
              </div>
              <div className="mt-0.5 text-[12.5px] text-home-muted">
                Discover chat personas, notification plugins, and more.
              </div>
            </div>
            <ArrowRight
              className="h-4 w-4 shrink-0 text-home-faint transition-colors group-hover:text-home-secondary"
              strokeWidth={2}
            />
          </button>
        </div>
      </div>
    </div>
  )
}

// Register this panel as the Hub's Connect-stage content at import time (the slot
// contract: Track 5 owns the chrome, the content side drops its tray in from its
// own module). Idempotent; a side-effect import from main.tsx pulls this module in
// before the Hub can open the Connect stage.
registerHubConnectContent(ConnectionsPanel)
