import { useEffect, useRef, useState } from 'react'
import { toast } from '../../../../lib/toast'
import {
  getCalendarStatus,
  getCalendarOAuthUrl,
  disconnectCalendar,
  pollUntilConnected,
  type CalendarStatus
} from '../../../../lib/calendarConnect'
import { ConnectorRow, PillButton } from './ConnectorRow'
import { ConnectorBrandMark } from './ConnectorBrandMark'

// Google Calendar via the BACKEND-mediated lane — works out of the box with no
// client-side Google credentials. Connect opens the system browser, then we POLL
// the integration status until the backend reports connected (the success deep
// link targets a scheme Windows doesn't register, so polling is the reliable
// signal). See lib/calendarConnect.ts.

// Phase-1 poll: 2s cadence, up to 2 minutes — matches the X connector's connect poll.
const POLL_INTERVAL_MS = 2000
const POLL_MAX_ATTEMPTS = 60

export function CalendarConnector(): React.JSX.Element {
  const [status, setStatus] = useState<CalendarStatus>({ connected: false })
  const [connecting, setConnecting] = useState(false)
  const [busy, setBusy] = useState(false)
  // Flipped on unmount so an in-flight poll stops touching state after the panel closes.
  const canceled = useRef(false)
  useEffect(() => {
    canceled.current = false
    getCalendarStatus()
      .then((s) => !canceled.current && setStatus(s))
      .catch(() => {})
    return () => {
      canceled.current = true
    }
  }, [])

  const connect = async (): Promise<void> => {
    if (connecting || busy) return
    setConnecting(true)
    try {
      const url = await getCalendarOAuthUrl()
      await window.omi.openExternalUrl(url)
      const ok = await pollUntilConnected(getCalendarStatus, {
        intervalMs: POLL_INTERVAL_MS,
        maxAttempts: POLL_MAX_ATTEMPTS,
        canceled: () => canceled.current
      })
      if (canceled.current) return
      if (ok) {
        setStatus(await getCalendarStatus())
        toast('Google Calendar connected', { tone: 'success' })
      } else {
        toast('Still waiting for Google Calendar', {
          tone: 'warn',
          body: 'Finish the sign-in in your browser, then reopen this panel to check.'
        })
      }
    } catch (e) {
      if (!canceled.current)
        toast('Could not start Calendar sign-in', { tone: 'error', body: (e as Error).message })
    } finally {
      if (!canceled.current) setConnecting(false)
    }
  }

  const disconnect = async (): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      await disconnectCalendar()
      setStatus({ connected: false })
      toast('Google Calendar disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }

  const description = status.connected
    ? `Connected${status.lastSyncAt ? ` · synced ${new Date(status.lastSyncAt).toLocaleDateString()}` : ''}`
    : 'Import events and recurring routines.'

  return (
    <ConnectorRow
      iconNode={<ConnectorBrandMark brand="calendar" />}
      title="Calendar"
      description={description}
      action={
        status.connected ? (
          <PillButton tone="ghost" onClick={disconnect} disabled={busy}>
            Disconnect
          </PillButton>
        ) : (
          <PillButton tone="primary" onClick={connect} disabled={connecting}>
            {connecting ? 'Waiting…' : 'Connect'}
          </PillButton>
        )
      }
    />
  )
}
