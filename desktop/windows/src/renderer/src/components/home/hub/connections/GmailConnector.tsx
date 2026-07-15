import { useEffect, useState } from 'react'
import { Mail } from 'lucide-react'
import { toast } from '../../../../lib/toast'
import { useMemories } from '../../../../hooks/useMemories'
import { runGoogleSync } from '../../../../lib/googleSync'
import { GOOGLE_ENABLED } from '../../../../lib/googleFeatureFlag'
import { ConnectorRow, PillButton } from './ConnectorRow'
import type { GoogleStatus } from '../../../../../../shared/types'

// Email (Gmail) via the CLIENT-SIDE loopback OAuth lane — turns recent email
// subjects/senders into memories. This lane needs a Google client id compiled into
// the build (main-side), so on a shipped build it's config-gated and the row shows
// a clean, non-dead "requires configuration" state. Calendar is a separate card on
// the backend lane; see CalendarConnector. Logic shared with Settings via
// window.omi.google* + lib/googleSync.ts.

export function GmailConnector(): React.JSX.Element {
  const { memories, refresh } = useMemories()
  const [status, setStatus] = useState<GoogleStatus>({ connected: false })
  const [busy, setBusy] = useState(false)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    if (!GOOGLE_ENABLED) return
    window.omi
      .googleStatus()
      .then(setStatus)
      .catch(() => {})
  }, [])

  const runSync = async (): Promise<void> => {
    if (syncing) return
    setSyncing(true)
    try {
      const out = await runGoogleSync(memories.map((m) => m.content))
      if (out.errors.length > 0)
        toast('Sync finished with errors', { tone: 'warn', body: out.errors.join('; ') })
      else
        toast(`Synced — ${out.memoriesAdded} memor${out.memoriesAdded === 1 ? 'y' : 'ies'} added`, {
          tone: 'success'
        })
      if (out.memoriesAdded > 0) await refresh()
      await window.omi.googleStatus().then(setStatus)
    } catch (e) {
      toast('Google sync failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setSyncing(false)
    }
  }

  const connect = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      const next = await window.omi.googleConnect()
      setStatus(next)
      if (next.connected) {
        toast('Google connected', { tone: 'success', body: next.email })
        void runSync()
      }
    } catch (e) {
      toast('Could not connect Google', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const disconnect = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      setStatus(await window.omi.googleDisconnect())
      toast('Google disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  if (!GOOGLE_ENABLED) {
    return (
      <ConnectorRow
        icon={Mail}
        title="Email"
        description="Import email history and follow-ups. Requires Google sign-in to be configured in this build."
      />
    )
  }

  const description = status.connected
    ? `Connected${status.email ? ` as ${status.email}` : ''}${
        status.lastSyncAt ? ` · synced ${new Date(status.lastSyncAt).toLocaleDateString()}` : ''
      }`
    : 'Import email history and follow-ups.'

  return (
    <ConnectorRow
      icon={Mail}
      title="Email"
      description={description}
      action={
        status.connected ? (
          <>
            <PillButton tone="neutral" onClick={runSync} disabled={syncing}>
              {syncing ? 'Syncing…' : 'Sync now'}
            </PillButton>
            <PillButton tone="ghost" onClick={disconnect} disabled={busy}>
              Disconnect
            </PillButton>
          </>
        ) : (
          <PillButton tone="primary" onClick={connect} disabled={busy}>
            {busy ? 'Connecting…' : 'Connect'}
          </PillButton>
        )
      }
    />
  )
}
