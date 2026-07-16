import { useEffect, useState } from 'react'
import { getCloudInfo, openCloudConnector } from '../../../../lib/mcpConnect'
import type {
  McpCloudConnectorId,
  McpCloudConnectorInfo
} from '../../../../../../shared/mcpExports'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'
import { McpCopyRow } from './McpCopyRow'

// The assisted cloud (OAuth) connector — ChatGPT or Claude. These connect over
// the provider's OWN OAuth flow against Omi's public PKCE client (no hosted key).
// Omi can't drive the provider's form, so "Open & guide me" opens the provider's
// connector page and reveals a guide card of copy-rows the user pastes in
// (mirrors macOS's guidance overlay — the parked browser automation is NOT
// ported). Connected state comes from the backend OAuth grants list.

export function McpCloudConnectorCard({ id }: { id: McpCloudConnectorId }): React.JSX.Element {
  const [info, setInfo] = useState<McpCloudConnectorInfo | undefined>()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let alive = true
    const load = async (): Promise<void> => {
      const all = await getCloudInfo().catch(() => [])
      if (alive) setInfo(all.find((i) => i.id === id))
    }
    void load()
    const off = window.omi?.onMcpChanged?.(() => {
      void load()
    })
    return () => {
      alive = false
      off?.()
    }
  }, [id])

  const connected = info?.connected ?? false

  const openGuide = (): void => {
    setOpen(true)
    if (info) void openCloudConnector(info.connectorUrl)
  }

  const description = connected
    ? `Connected — your Omi memory is available in ${info?.title ?? 'this app'}`
    : `Connect over OAuth — no key needed`

  return (
    <ConnectorRow
      iconNode={<ConnectorBrandMark brand={id} />}
      title={info?.title ?? (id === 'claude' ? 'Claude' : 'ChatGPT')}
      description={description}
      action={
        <PillButton tone={connected ? 'neutral' : 'primary'} onClick={openGuide}>
          {connected ? 'Reconnect' : 'Open & guide'}
        </PillButton>
      }
    >
      {open && info && (
        <div className="space-y-2 rounded-xl border border-home-hairline bg-white/[0.02] p-3">
          <p className="text-[12.5px] text-home-muted">
            {info.title} opened in your browser. Add a custom connector and paste these values:
          </p>
          <div className="flex flex-col divide-y divide-home-hairline">
            {info.rows.map((row) => (
              <McpCopyRow key={row.label} row={row} />
            ))}
          </div>
        </div>
      )}
    </ConnectorRow>
  )
}
