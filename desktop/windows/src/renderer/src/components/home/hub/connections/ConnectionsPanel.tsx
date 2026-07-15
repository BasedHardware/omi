import { useNavigate } from 'react-router-dom'
import { LayoutGrid, ArrowRight } from 'lucide-react'
import type { HubConnectSlotProps } from '../hubConnectSlot'
import { CalendarConnector } from './CalendarConnector'
import { GmailConnector } from './GmailConnector'
import { StickyNotesConnector } from './StickyNotesConnector'
import { PasteImportConnector } from './PasteImportConnector'
import { ExportsConnector } from './ExportsConnector'
import { ConnectorRow } from './ConnectorRow'

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
// calendar, email, local-files, apple-notes, x, chatgpt, claude), rendered in
// declaration order (connection state affects only labels, never position). Windows
// drops Local Files (it lives in Settings → Advanced / file indexing) and maps Apple
// Notes → Sticky Notes.
//
// SLOT CONTRACT: mount at 100%/100%, own the internal scroll (the Hub panel is
// overflow-hidden), never set an outer fixed size. Registered lazily from
// register.ts (a dynamic import) so this module graph loads only when the main
// window first opens Connect — see hubConnectSlot.ts.

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
        {/* Flat pure-white title — no gradient, no glow, no stage-glow var. The only
            sanctioned violet is the panel's background chrome (owned by Track 5). */}
        <h1 className="font-display text-[22px] font-bold lowercase leading-none text-white">
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

          {/* Rendered through ConnectorRow (as a button) so it shares the row's exact
              layout/styling instead of re-declaring it. */}
          <ConnectorRow
            icon={LayoutGrid}
            title="Browse the App Marketplace"
            description="Discover chat personas, notification plugins, and more."
            onClick={openApps}
            action={<ArrowRight className="h-4 w-4 text-home-faint" strokeWidth={2} />}
          />
        </div>
      </div>
    </div>
  )
}
