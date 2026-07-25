import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { toast } from '../../../../lib/toast'
import { rotateMcpKey } from '../../../../lib/mcpConnect'
import { useMcpExports } from '../../../../hooks/useMcpExports'
import {
  MCP_CONFIG_CONNECTORS,
  type McpConnectorId,
  type McpCloudConnectorId
} from '../../../../../../shared/mcpExports'
import { McpConfigConnectorRow } from './McpConfigConnectorRow'
import { McpCloudConnectorCard } from './McpCloudConnectorCard'
import { MemoryPackRow } from './MemoryPackRow'

// The detail body for one export destination in the "Use omi memory anywhere"
// column. Each destination shows its config-write connector(s) — the row that
// actually gives an external tool read access to Omi memory via the hosted MCP
// endpoint. When this account has a hosted key, a quiet "Rotate key" control
// lets the user revoke + re-mint (rewriting any connected configs).
//
// ChatGPT/Claude also get the assisted cloud (OAuth) connector card and a
// memory-pack row beneath the config connector; OpenClaw/Hermes show only their
// gated config connector.

// Which config connectors belong under each export destination tile.
const CONNECTORS_FOR: Record<string, McpConnectorId[]> = {
  claude: ['claudeCode'],
  chatgpt: ['codex'],
  openclaw: ['openclaw'],
  hermes: ['hermes']
}

// Which destinations also offer a cloud (OAuth) connector + a memory-pack row.
const CLOUD_FOR: Record<string, McpCloudConnectorId | undefined> = {
  claude: 'claude',
  chatgpt: 'chatgpt'
}
const PACK_FOR: Record<string, 'chatgpt' | 'claude' | undefined> = {
  claude: 'claude',
  chatgpt: 'chatgpt'
}

export function McpExportDetail({ exportId }: { exportId: string }): React.JSX.Element {
  const { snapshot, statusFor, refresh } = useMcpExports()
  const [rotating, setRotating] = useState(false)

  const ids = CONNECTORS_FOR[exportId] ?? []
  const connectors = MCP_CONFIG_CONNECTORS.filter((c) => ids.includes(c.id))
  const anyConnected = connectors.some((c) => statusFor(c.id)?.kind === 'connected')
  const cloudId = CLOUD_FOR[exportId]
  const packProvider = PACK_FOR[exportId]

  const rotate = async (): Promise<void> => {
    if (rotating) return
    setRotating(true)
    try {
      await rotateMcpKey()
      await refresh()
      toast('Rotated your Omi memory key', { tone: 'success' })
    } catch (e) {
      toast('Could not rotate key', { tone: 'error', body: (e as Error).message })
    } finally {
      setRotating(false)
    }
  }

  return (
    <div className="flex flex-col">
      <div className="flex flex-col">
        {connectors.map((connector) => (
          <McpConfigConnectorRow
            key={connector.id}
            connector={connector}
            status={statusFor(connector.id)}
            onChanged={refresh}
          />
        ))}
        {cloudId && <McpCloudConnectorCard id={cloudId} />}
        {packProvider && <MemoryPackRow provider={packProvider} />}
      </div>

      {/* Hosted-key management — only meaningful once a key exists (something is
          connected, or the account already minted one). Quiet, secondary. */}
      {(anyConnected || snapshot?.hasKey) && (
        <button
          type="button"
          onClick={rotate}
          disabled={rotating}
          className="focus-ring mt-4 inline-flex items-center gap-1.5 self-start rounded-lg py-1 pl-1 pr-2 text-[12px] font-medium text-home-muted transition-colors hover:text-home-ink disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${rotating ? 'animate-spin' : ''}`} strokeWidth={2} />
          {rotating ? 'Rotating…' : 'Rotate memory key'}
        </button>
      )}
    </div>
  )
}
