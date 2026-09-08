import { useCallback, useEffect, useState } from 'react'
import { getMcpStatus } from '../lib/mcpConnect'
import type { McpConnectorStatus, McpExportsSnapshot } from '../../../shared/mcpExports'

// Loads the MCP export-connector status for the signed-in account and keeps it
// fresh: main broadcasts `mcp:changed` after any connect/disconnect/rotate, and
// we re-read. Returns a per-connector lookup so a row can render its own state
// without threading the whole snapshot.
export function useMcpExports(): {
  snapshot: McpExportsSnapshot | null
  statusFor: (id: McpConnectorStatus['id']) => McpConnectorStatus | undefined
  loading: boolean
  refresh: () => Promise<void>
} {
  const [snapshot, setSnapshot] = useState<McpExportsSnapshot | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    const s = await getMcpStatus().catch(() => null)
    setSnapshot(s)
    setLoading(false)
  }, [])

  useEffect(() => {
    let alive = true
    void (async () => {
      const s = await getMcpStatus().catch(() => null)
      if (alive) {
        setSnapshot(s)
        setLoading(false)
      }
    })()
    const off = window.omi?.onMcpChanged?.(() => {
      void refresh()
    })
    return () => {
      alive = false
      off?.()
    }
  }, [refresh])

  const statusFor = useCallback(
    (id: McpConnectorStatus['id']) => snapshot?.connectors.find((c) => c.id === id),
    [snapshot]
  )

  return { snapshot, statusFor, loading, refresh }
}
