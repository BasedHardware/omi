import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, LayoutGrid, ArrowRight, X } from 'lucide-react'
import type { HubConnectSlotProps } from '../hubConnectSlot'
import { CalendarConnector } from './CalendarConnector'
import { GmailConnector } from './GmailConnector'
import { StickyNotesConnector } from './StickyNotesConnector'
import { XConnector } from './XConnector'
import { PasteImportConnector } from './PasteImportConnector'
import { ExportsConnector } from './ExportsConnector'
import { ConnectorRow } from './ConnectorRow'
import { ConnectTray } from './ConnectTray'
import { McpExportDetail } from './McpExportDetail'

// The Connections home — the content registered into the Hub's Connect stage (see
// hubConnectSlot.ts). The Windows-native port of macOS's DashboardPage connect tray.
//
// TWO LEVELS, one shallow internal navigator (no router — this lives inside a Hub
// stage, so it owns its own view state):
//   • TRAY (top level) — Mac's homeConnectPanel: two columns, "Connect data" (import
//     SOURCES) and "Use omi memory anywhere" (export DESTINATIONS). Each tile drills
//     into that connector's detail; "+ More" opens the full list for that side.
//   • DETAIL (level 2) — a single connector's flow, or the full Imports / Exports
//     lists, each reached from the tray and returning to it via Back.
//
// All connect/sync/import/export logic is shared with Settings via the lib/* services
// each connector imports — this panel adds only Hub-native presentation + navigation.
// Import order mirrors Mac's static curated array (calendar, email, notes, x, chatgpt,
// claude); Windows drops Local Files and maps Apple Notes → Sticky Notes.
//
// SLOT CONTRACT: mount at 100%/100%, own the internal scroll (the Hub panel is
// overflow-hidden), never set an outer fixed size. Registered lazily from register.ts.

const OMI_DEVICE_URL = 'https://www.omi.me'

type ExportId = 'claude' | 'chatgpt' | 'openclaw' | 'hermes'

type View =
  | { kind: 'tray' }
  | { kind: 'source'; id: 'gmail' | 'calendar' | 'sticky' | 'x' }
  | { kind: 'imports' }
  | { kind: 'exports' }
  | { kind: 'export'; id: ExportId }

// Title shown in the DetailShell header for each export destination.
const EXPORT_TITLES: Record<ExportId, string> = {
  claude: 'Claude / Claude Code',
  chatgpt: 'ChatGPT / Codex',
  openclaw: 'OpenClaw',
  hermes: 'Hermes'
}

function SectionHeader({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <h2 className="mb-1 font-serif text-[17px] font-medium text-home-secondary">{children}</h2>
}

// Level-2 chrome: a Back affordance (returns to the tray) and a close X, wrapping the
// detail content in the panel's own scroll region.
function DetailShell({
  title,
  onBack,
  onDismiss,
  children
}: {
  title: string
  onBack: () => void
  onDismiss: () => void
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <div className="relative flex h-full w-full flex-col" data-testid="connections-detail">
      <div className="flex shrink-0 items-center gap-2.5 px-5 pt-5">
        <button
          type="button"
          onClick={onBack}
          data-testid="connections-back"
          className="focus-ring -ml-1.5 flex items-center gap-1 rounded-lg py-1 pl-1 pr-2 text-[13px] font-medium text-home-muted transition-colors hover:text-home-ink"
        >
          <ChevronLeft className="h-4 w-4" strokeWidth={2.25} />
          Back
        </button>
        <h1 className="min-w-0 truncate font-serif text-[18px] font-medium text-home-ink">
          {title}
        </h1>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Close connect"
          className="focus-ring ml-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-home-muted transition-colors hover:bg-white/10 hover:text-home-ink"
        >
          <X className="h-4 w-4" strokeWidth={2} />
        </button>
      </div>
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto px-5 pb-6">
        <div className="mx-auto w-full max-w-[720px]">{children}</div>
      </div>
    </div>
  )
}

// The App Marketplace link — rendered through ConnectorRow so it shares the exact row
// layout; kept reachable from the list views (Mac's "More" opens the apps popup).
function MarketplaceLink({ onOpen }: { onOpen: () => void }): React.JSX.Element {
  return (
    <ConnectorRow
      icon={LayoutGrid}
      title="Browse the App Marketplace"
      description="Discover chat personas, notification plugins, and more."
      onClick={onOpen}
      action={<ArrowRight className="h-4 w-4 text-home-faint" strokeWidth={2} />}
    />
  )
}

export function ConnectionsPanel({ onDismiss }: HubConnectSlotProps): React.JSX.Element {
  const navigate = useNavigate()
  const [view, setView] = useState<View>({ kind: 'tray' })

  const openApps = (): void => {
    onDismiss()
    navigate('/apps')
  }

  // "Ask Omi": leave the Connect stage and hand focus to the hub's ask bar. The slot
  // gives us only onDismiss, so we reach the bar the way HomeHub identifies it (a
  // stable testid) once React has re-mounted the resting hub — two frames is enough
  // for the panel→hub transition to commit.
  const askOmi = (): void => {
    onDismiss()
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        document.querySelector<HTMLInputElement>('[data-testid="hub-ask-bar"] input')?.focus()
      })
    )
  }

  const openDevice = (): void => {
    void window.omi.openExternalUrl(OMI_DEVICE_URL)
  }

  if (view.kind === 'tray') {
    return (
      <ConnectTray
        onOpenSource={(id) => setView({ kind: 'source', id })}
        onOpenImports={() => setView({ kind: 'imports' })}
        onOpenExports={() => setView({ kind: 'exports' })}
        onOpenExport={(id) => setView({ kind: 'export', id })}
        onAskOmi={askOmi}
        onOpenDevice={openDevice}
        onDismiss={onDismiss}
      />
    )
  }

  const back = (): void => setView({ kind: 'tray' })

  if (view.kind === 'source') {
    const detail =
      view.id === 'gmail' ? (
        <GmailConnector />
      ) : view.id === 'calendar' ? (
        <CalendarConnector />
      ) : view.id === 'x' ? (
        <XConnector />
      ) : (
        <StickyNotesConnector />
      )
    return (
      <DetailShell title="Connect data" onBack={back} onDismiss={onDismiss}>
        <div className="flex flex-col">{detail}</div>
      </DetailShell>
    )
  }

  if (view.kind === 'imports') {
    return (
      <DetailShell title="Import sources" onBack={back} onDismiss={onDismiss}>
        <SectionHeader>Imports</SectionHeader>
        <div className="flex flex-col">
          <CalendarConnector />
          <GmailConnector />
          <StickyNotesConnector />
          <XConnector />
          <PasteImportConnector source="chatgpt" />
          <PasteImportConnector source="claude" />
        </div>
        <div className="mt-6">
          <MarketplaceLink onOpen={openApps} />
        </div>
      </DetailShell>
    )
  }

  if (view.kind === 'exports') {
    return (
      <DetailShell title="Use omi memory anywhere" onBack={back} onDismiss={onDismiss}>
        <SectionHeader>Exports</SectionHeader>
        <div className="flex flex-col">
          <ExportsConnector />
        </div>
        <div className="mt-6">
          <MarketplaceLink onOpen={openApps} />
        </div>
      </DetailShell>
    )
  }

  // export — a single destination's connect/detail (Claude·Claude Code,
  // ChatGPT·Codex, OpenClaw, Hermes): the real MCP memory-bank connectors that
  // give an external tool read access to your Omi memory.
  return (
    <DetailShell title={EXPORT_TITLES[view.id]} onBack={back} onDismiss={onDismiss}>
      <SectionHeader>Use omi memory anywhere</SectionHeader>
      <McpExportDetail exportId={view.id} />
      <div className="mt-6">
        <MarketplaceLink onOpen={openApps} />
      </div>
    </DetailShell>
  )
}
