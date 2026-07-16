import { useEffect, useRef, useState } from 'react'
import { ChevronRight, X } from 'lucide-react'
import { useGoogleConnection } from '../../../../hooks/useGoogleConnection'
import { getCalendarStatus, type CalendarStatus } from '../../../../lib/calendarConnect'
import { getXSession } from '../../../../lib/xSession'
import type { XStatus } from '../../../../../../shared/types'
import { TrayTile } from './TrayTile'

// The Connections tray — the top level of the Connect stage, and the faithful port
// of macOS's homeConnectPanel (DashboardPage.swift): two rounded column cards under
// serif headers with a chevron between them. LEFT is data Omi learns FROM (import
// sources); RIGHT is where Omi's memory flows OUT (AI destinations). Each tile
// drills into that connector's detail; the "+ More" tiles open the full list views.
//
// This renders inside HubConnectPanel's chrome (the outer bordered panel), so the
// column CARDS are the nested rounded surfaces you see in the design — the tray adds
// no second outer frame. All navigation is owned by ConnectionsPanel and passed in.

export interface ConnectTrayCallbacks {
  /** LEFT brand tile → that import connector's detail (drill-in). */
  onOpenSource: (id: 'gmail' | 'calendar' | 'sticky' | 'x') => void
  /** LEFT "+ More" → the full Imports list. */
  onOpenImports: () => void
  /** RIGHT "+ More" → the Exports (memory-pack) list. */
  onOpenExports: () => void
  /** RIGHT brand tile → that export destination's connect/detail view. */
  onOpenExport: (id: 'claude' | 'chatgpt' | 'openclaw' | 'hermes') => void
  /** RIGHT "Ask Omi" → close the panel and focus the hub ask bar. */
  onAskOmi: () => void
  /** LEFT "Omi Device" → open the omi.me device page (no drill-in, like Mac). */
  onOpenDevice: () => void
  /** The close X (top-right) → dismiss the Connect stage. */
  onDismiss: () => void
}

function ColumnHeader({ title, subtitle }: { title: string; subtitle: string }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="font-serif text-[20px] font-medium leading-none text-home-ink">{title}</h2>
      <p className="text-[12px] font-medium text-home-muted">{subtitle}</p>
    </div>
  )
}

function ColumnCard({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3 rounded-[22px] border border-home-hairline bg-white/[0.02] p-4">
      {children}
    </div>
  )
}

export function ConnectTray(props: ConnectTrayCallbacks): React.JSX.Element {
  const {
    onOpenSource,
    onOpenImports,
    onOpenExports,
    onOpenExport,
    onAskOmi,
    onOpenDevice,
    onDismiss
  } = props

  // Connected labels reuse the SAME status derivations the connectors do — the Gmail
  // lane's shared singleton hook, and a one-shot Calendar status probe. Sticky Notes
  // is a one-shot import with no persistent connection, and Windows has no
  // Omi-device-history signal yet, so those tiles carry no "Connected" label.
  const { googleEnabled, status: gmailStatus } = useGoogleConnection()
  const gmailConnected = googleEnabled && gmailStatus.connected

  const [calendar, setCalendar] = useState<CalendarStatus>({ connected: false })
  const canceled = useRef(false)
  useEffect(() => {
    canceled.current = false
    getCalendarStatus()
      .then((s) => !canceled.current && setCalendar(s))
      .catch(() => {})
    return () => {
      canceled.current = true
    }
  }, [])

  // X status via the main-process xStatus (see lib/xSession + XConnector). Signed out
  // or an unconfigured backend just leaves the tile without a "Connected" label.
  // Own cancellation ref (not the Calendar effect's) so this effect stays correct
  // independently of it.
  const [xConnected, setXConnected] = useState(false)
  const xCanceled = useRef(false)
  useEffect(() => {
    xCanceled.current = false
    void (async () => {
      const session = await getXSession()
      if (!session || xCanceled.current) return
      try {
        const s: XStatus = await window.omi.xStatus(session)
        if (!xCanceled.current) setXConnected(s.connected)
      } catch {
        /* not configured / not connected — leave the label off */
      }
    })()
    return () => {
      xCanceled.current = true
    }
  }, [])

  return (
    <div className="relative flex h-full w-full flex-col" data-testid="connect-tray">
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Close connect"
        data-testid="connect-tray-close"
        className="focus-ring absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-full text-home-muted transition-colors hover:bg-white/10 hover:text-home-ink"
      >
        <X className="h-4 w-4" strokeWidth={2} />
      </button>

      <div className="flex-1 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center px-5 py-6">
          <div className="flex w-full max-w-[920px] items-stretch gap-2.5">
            <ColumnCard>
              <ColumnHeader title="Connect data" subtitle="Sources Omi learns from." />
              <div className="flex flex-col gap-2.5">
                <TrayTile
                  title="Gmail"
                  brand="gmail"
                  connected={gmailConnected}
                  onClick={() => onOpenSource('gmail')}
                />
                <TrayTile
                  title="Calendar"
                  brand="calendar"
                  connected={calendar.connected}
                  onClick={() => onOpenSource('calendar')}
                />
                <TrayTile
                  title="Sticky Notes"
                  brand="sticky"
                  onClick={() => onOpenSource('sticky')}
                />
                <TrayTile
                  title="X (Twitter)"
                  brand="x"
                  connected={xConnected}
                  onClick={() => onOpenSource('x')}
                />
                <TrayTile title="Omi Device" brand="omi" onClick={onOpenDevice} />
                <TrayTile
                  title="More"
                  plus
                  testId="tray-tile-more-imports"
                  onClick={onOpenImports}
                />
              </div>
            </ColumnCard>

            <div className="flex shrink-0 items-center" aria-hidden>
              <span className="flex h-[30px] w-[30px] items-center justify-center rounded-full border border-home-hairline bg-home-tile">
                <ChevronRight className="h-3.5 w-3.5 text-home-secondary" strokeWidth={2.5} />
              </span>
            </div>

            <ColumnCard>
              <ColumnHeader
                title="Use omi memory anywhere"
                subtitle="Bring your memories to the apps you use"
              />
              <div className="flex flex-col gap-2.5">
                <TrayTile title="Ask Omi" brand="omi" onClick={onAskOmi} />
                <TrayTile
                  title="Claude / Claude Code"
                  brand="claude"
                  onClick={() => onOpenExport('claude')}
                />
                <TrayTile
                  title="ChatGPT / Codex"
                  brand="chatgpt"
                  onClick={() => onOpenExport('chatgpt')}
                />
                <TrayTile title="OpenClaw" brand="openclaw" onClick={() => onOpenExport('openclaw')} />
                <TrayTile title="Hermes" brand="hermes" onClick={() => onOpenExport('hermes')} />
                <TrayTile
                  title="More"
                  plus
                  testId="tray-tile-more-exports"
                  onClick={onOpenExports}
                />
              </div>
            </ColumnCard>
          </div>
        </div>
      </div>
    </div>
  )
}
