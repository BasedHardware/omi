import { useEffect, useState } from 'react'
import { toast } from '../../../../lib/toast'
import { useMemories } from '../../../../hooks/useMemories'
import { getXSession } from '../../../../lib/xSession'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'
import type { XStatus, XRunState } from '../../../../../../shared/types'

// X (Twitter) connector row. The connect run lives in main (so it outlives this
// panel); here we relay the session, kick it off, and reflect the streamed run
// state (connecting → syncing with live counts → succeeded). See main/integrations/
// xConnector.ts.

const IDLE_RUN: XRunState = { phase: 'idle', postCount: 0, memoryCount: 0 }

function friendlyError(err?: string): string {
  if (err === 'x_oauth_not_configured' || err === 'unknown' || err === 'no_auth_url')
    return "X connector isn't configured on the server yet."
  if (err === 'timeout')
    return 'Timed out waiting for X. Finish the sign-in in your browser, then try again.'
  return err ?? 'Something went wrong.'
}

export function XConnector(): React.JSX.Element {
  const { refresh } = useMemories()
  const [status, setStatus] = useState<XStatus | null>(null)
  const [run, setRun] = useState<XRunState>(IDLE_RUN)

  useEffect(() => {
    let live = true
    void (async () => {
      const session = await getXSession()
      if (!session || !live) return
      xStatusSafe(session).then((s) => live && s && setStatus(s))
      window.omi
        .xRunState()
        .then((r) => live && setRun(r))
        .catch(() => {})
    })()
    const off = window.omi.onXProgress((r) => {
      setRun(r)
      if (r.phase === 'succeeded') {
        void refresh()
        void refreshStatus()
      }
    })
    return () => {
      live = false
      off()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshStatus = async (): Promise<void> => {
    const session = await getXSession()
    if (session) setStatus(await xStatusSafe(session))
  }

  const connect = async (): Promise<void> => {
    const session = await getXSession()
    if (!session) {
      toast('Sign in to connect X', { tone: 'warn' })
      return
    }
    setRun(await window.omi.xConnect(session)) // seeds 'connecting'; progress streams in
  }

  const sync = async (): Promise<void> => {
    const session = await getXSession()
    if (!session) return
    try {
      const r = await window.omi.xSync(session)
      if (r.success)
        toast(`Synced X — ${r.newPosts} new post${r.newPosts === 1 ? '' : 's'}`, {
          tone: 'success'
        })
      else toast('X sync failed', { tone: 'error', body: friendlyError(r.error) })
      await refreshStatus()
      if (r.memoriesCreated > 0) await refresh()
    } catch (e) {
      toast('X sync failed', { tone: 'error', body: (e as Error).message })
    }
  }

  const disconnect = async (): Promise<void> => {
    const session = await getXSession()
    if (!session) return
    try {
      await window.omi.xDisconnect(session)
      setStatus({ connected: false, postCount: 0, memoryCount: 0, syncing: false })
      setRun(IDLE_RUN)
      toast('X disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    }
  }

  const view = deriveView(status, run)

  return (
    <ConnectorRow
      iconNode={<ConnectorBrandMark brand="x" />}
      title="X (Twitter)"
      description={view.description}
      action={
        view.state === 'connected' ? (
          <>
            <PillButton tone="neutral" onClick={sync} disabled={status?.syncing}>
              {status?.syncing ? 'Syncing…' : 'Sync now'}
            </PillButton>
            <PillButton tone="ghost" onClick={disconnect}>
              Disconnect
            </PillButton>
          </>
        ) : view.state === 'busy' ? (
          <PillButton tone="primary" disabled>
            {run.phase === 'syncing' ? 'Importing…' : 'Waiting…'}
          </PillButton>
        ) : (
          <PillButton tone="primary" onClick={connect}>
            Connect
          </PillButton>
        )
      }
    />
  )
}

export type XView = { state: 'connected' | 'busy' | 'idle'; description: React.ReactNode }

// Precedence: an in-flight run drives the view; otherwise the connection status.
export function deriveView(status: XStatus | null, run: XRunState): XView {
  if (run.phase === 'connecting')
    return {
      state: 'busy',
      description: 'Waiting for X sign-in… you can close this panel; Omi keeps importing.'
    }
  if (run.phase === 'syncing')
    return {
      state: 'busy',
      description: `Saved ${run.postCount} post${run.postCount === 1 ? '' : 's'} · ${run.memoryCount} memor${run.memoryCount === 1 ? 'y' : 'ies'} so far…`
    }
  const connected = status?.connected || run.phase === 'succeeded'
  if (connected) {
    const handle = status?.handle ?? run.handle
    const posts = status?.postCount ?? run.postCount
    const mems = status?.memoryCount ?? run.memoryCount
    return {
      state: 'connected',
      description: `Connected${handle ? ` as @${handle}` : ''} · ${posts} post${posts === 1 ? '' : 's'}, ${mems} memor${mems === 1 ? 'y' : 'ies'}`
    }
  }
  if (run.phase === 'failed') return { state: 'idle', description: friendlyError(run.error) }
  return {
    state: 'idle',
    description: 'Connect your X account so Omi learns from your tweets and bookmarks.'
  }
}

// xStatus can legitimately fail (not configured / not connected yet); treat any
// failure as "not connected" rather than surfacing an error on mount.
async function xStatusSafe(session: { apiBase: string; token: string }): Promise<XStatus> {
  try {
    return await window.omi.xStatus(session)
  } catch {
    return { connected: false, postCount: 0, memoryCount: 0, syncing: false }
  }
}
