import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { toast } from '../../../../lib/toast'
import { connectMcp, copyMcpSetup, disconnectMcp } from '../../../../lib/mcpConnect'
import type {
  McpConfigConnector,
  McpConnectorId,
  McpConnectorStatus,
  McpSetupCard
} from '../../../../../../shared/mcpExports'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'

// One config-write export connector row (Claude Code, Codex, OpenClaw, Hermes).
// Every state resolves to a real affordance — never a dead button:
//   • connected    → "Connected" + a Disconnect pill
//   • available    → the tool is present → a Connect pill (mints the hosted key
//                    on first use and writes the tool's MCP config)
//   • requiresTool → the CLI/config isn't on this machine → a plain "requires
//                    <tool>" line, no action
// When a CLI connector's one-click automation fails, connect returns a manual
// setup card (copy-command) that we reveal below the row (Mac's fallback path).
// The hosted key never reaches the renderer; connect/disconnect are IPC calls.

function description(
  connector: McpConfigConnector,
  status: McpConnectorStatus | undefined
): string {
  if (!status) return 'Checking…'
  switch (status.kind) {
    case 'connected':
      return 'Connected — reading your Omi memory'
    case 'available':
      return `Give ${connector.tool} access to your Omi memory`
    case 'requiresTool':
      return `Requires ${connector.tool}`
  }
}

function SetupCardBlock({
  card,
  connectorId
}: {
  card: McpSetupCard
  connectorId: McpConnectorId
}): React.JSX.Element {
  const [copied, setCopied] = useState(false)
  const copy = async (): Promise<void> => {
    try {
      await copyMcpSetup(connectorId)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch (e) {
      toast('Could not copy setup', { tone: 'error', body: (e as Error).message })
    }
  }
  return (
    <div className="space-y-2 rounded-xl border border-home-hairline bg-white/[0.02] p-3">
      <p className="text-[12.5px] text-home-muted">
        Couldn’t finish automatically — run this yourself to connect:
      </p>
      <ol className="ml-4 list-decimal space-y-0.5 text-[12.5px] text-home-muted">
        {card.steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <div className="flex items-center justify-end">
        <button
          type="button"
          onClick={copy}
          aria-label={copied ? 'Copied' : card.copyTitle}
          title={copied ? 'Copied' : card.copyTitle}
          className="focus-ring flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-home-muted transition-colors hover:bg-white/10 hover:text-home-ink"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5" strokeWidth={2.25} />
          ) : (
            <Copy className="h-3.5 w-3.5" strokeWidth={2} />
          )}
        </button>
      </div>
    </div>
  )
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
  const [card, setCard] = useState<McpSetupCard | undefined>()

  const doConnect = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      const result = await connectMcp(connector.id)
      // Automation fell back to a manual command — reveal it. Otherwise refresh.
      if (result?.setupCard) setCard(result.setupCard)
      else setCard(undefined)
      onChanged()
    } catch (e) {
      toast('Could not connect', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const doDisconnect = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      await disconnectMcp(connector.id)
      setCard(undefined)
      onChanged()
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const action = ((): React.ReactNode => {
    if (!status) return null
    switch (status.kind) {
      case 'connected':
        return (
          <PillButton tone="ghost" disabled={busy} onClick={doDisconnect}>
            {busy ? '…' : 'Disconnect'}
          </PillButton>
        )
      case 'available':
        return (
          <PillButton tone="primary" disabled={busy} onClick={doConnect}>
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
    >
      {card && <SetupCardBlock card={card} connectorId={connector.id} />}
    </ConnectorRow>
  )
}
