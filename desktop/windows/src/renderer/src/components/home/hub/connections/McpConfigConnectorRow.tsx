import { useState } from 'react'
import { toast } from '../../../../lib/toast'
import { connectMcp, disconnectMcp } from '../../../../lib/mcpConnect'
import type { McpConfigConnector, McpConnectorStatus } from '../../../../../../shared/mcpExports'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'

// One config-write export connector row (Claude Code, Codex, OpenClaw, Hermes).
// Every state resolves to a real affordance — never a dead button:
//   • connected    → "Connected" + a Disconnect pill
//   • available    → the tool is present → a Connect pill (mints the hosted key
//                    on first use and writes the tool's MCP config)
//   • requiresTool → the CLI/config isn't on this machine → a plain "requires
//                    <tool>" line, no action
// The hosted key never reaches the renderer; connect/disconnect are IPC calls.

function description(
  connector: McpConfigConnector,
  status: McpConnectorStatus | undefined
): string {
  if (!status) return 'Checking…'
  switch (status.kind) {
    case 'connected':
      return `Connected — reading your Omi memory`
    case 'available':
      return `Give ${connector.tool} access to your Omi memory`
    case 'requiresTool':
      return `Requires ${connector.tool}`
  }
}

export function McpConfigConnectorRow({
  connector,
  status,
  onChanged
}: {
  connector: McpConfigConnector
  status: McpConnectorStatus | undefined
  /** Called after a successful connect/disconnect so the parent can refresh. */
  onChanged: () => void
}): React.JSX.Element {
  const [busy, setBusy] = useState(false)

  const run = async (fn: () => Promise<unknown>, failMsg: string): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      await fn()
      onChanged()
    } catch (e) {
      toast(failMsg, { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const action = ((): React.ReactNode => {
    if (!status) return null
    switch (status.kind) {
      case 'connected':
        return (
          <PillButton
            tone="ghost"
            disabled={busy}
            onClick={() => run(() => disconnectMcp(connector.id), 'Could not disconnect')}
          >
            {busy ? '…' : 'Disconnect'}
          </PillButton>
        )
      case 'available':
        return (
          <PillButton
            tone="primary"
            disabled={busy}
            onClick={() => run(() => connectMcp(connector.id), 'Could not connect')}
          >
            {busy ? 'Connecting…' : 'Connect'}
          </PillButton>
        )
      case 'requiresTool':
        // Non-actionable — the tool isn't installed. The description says so.
        return null
    }
  })()

  return (
    <ConnectorRow
      iconNode={<ConnectorBrandMark brand={connector.brand} />}
      title={connector.title}
      description={description(connector, status)}
      action={action}
    />
  )
}
