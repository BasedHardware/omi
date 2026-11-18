import { useEffect, useRef, useState } from 'react'
import { onAuthStateChanged } from 'firebase/auth'
import { auth } from '../../lib/firebase'
import {
  getCalendarOAuthUrl,
  getCalendarStatus,
  pollUntilConnected
} from '../../lib/calendarConnect'
import {
  loadGoogleCalendarSelection,
  saveGoogleCalendarSelection,
  type OwnedCalendarSelection
} from '../../lib/googleCalendarSelection'

export function GoogleCalendarSelectionPanel(): React.JSX.Element {
  const [data, setData] = useState<OwnedCalendarSelection | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [saved, setSaved] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const lifecycle = useRef({ mounted: true, connectionSerial: 0 })

  useEffect(() => {
    const state = lifecycle.current
    state.mounted = true
    const unsubscribe = onAuthStateChanged(auth, () => {
      state.connectionSerial++
      setData(null)
      setSelected([])
      setBusy(false)
      setFailed(false)
      setSaved(false)
      setConnecting(false)
    })
    return () => {
      state.mounted = false
      state.connectionSerial++
      unsubscribe()
    }
  }, [])

  const connect = async (): Promise<void> => {
    const owner = auth.currentUser
    if (!owner || busy) return
    const attempt = ++lifecycle.current.connectionSerial
    const current = (): boolean =>
      lifecycle.current.mounted &&
      auth.currentUser === owner &&
      attempt === lifecycle.current.connectionSerial
    setBusy(true)
    setConnecting(true)
    setFailed(false)
    try {
      const url = await getCalendarOAuthUrl(current)
      if (!current()) return
      if (!(await window.omi.openExternalUrl(url))) throw new Error('Browser did not open')
      if (!current()) return
      const connected = await pollUntilConnected(() => getCalendarStatus(current), {
        intervalMs: 2000,
        maxAttempts: 60,
        canceled: () => !current()
      })
      if (!current()) return
      if (!connected) throw new Error('Calendar connection not completed')
      const result = await loadGoogleCalendarSelection()
      if (!current()) return
      setData(result)
      setSelected(result.selected_ids)
    } catch {
      if (current()) setFailed(true)
    } finally {
      if (current()) {
        setBusy(false)
        setConnecting(false)
      }
    }
  }

  const load = async (): Promise<void> => {
    const owner = auth.currentUser
    setBusy(true)
    setFailed(false)
    setSaved(false)
    setData(null)
    try {
      const result = await loadGoogleCalendarSelection()
      if (!lifecycle.current.mounted || auth.currentUser !== owner) return
      setData(result)
      setSelected(result.selected_ids)
    } catch {
      if (lifecycle.current.mounted && auth.currentUser === owner) setFailed(true)
    } finally {
      if (lifecycle.current.mounted && auth.currentUser === owner) setBusy(false)
    }
  }

  const save = async (): Promise<void> => {
    if (!data || !selected.length || busy) return
    setBusy(true)
    setFailed(false)
    setSaved(false)
    try {
      const result = await saveGoogleCalendarSelection(data, selected)
      if (!lifecycle.current.mounted || auth.currentUser !== data.owner) return
      setData(result)
      setSelected(result.selected_ids)
      setSaved(true)
    } catch {
      if (lifecycle.current.mounted && auth.currentUser === data.owner) setFailed(true)
    } finally {
      if (lifecycle.current.mounted && auth.currentUser === data.owner) setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <button className="btn-ghost disabled:opacity-40" disabled={busy} onClick={load}>
        {busy ? 'Working…' : 'Choose Calendars'}
      </button>
      {!data && (
        <button className="btn-ghost disabled:opacity-40" disabled={busy} onClick={connect}>
          Connect Google Calendar
        </button>
      )}
      {connecting && (
        <div>
          <p role="status">Finish Google sign-in in your browser.</p>
          <button
            className="btn-ghost"
            onClick={() => {
              lifecycle.current.connectionSerial++
              setConnecting(false)
              setBusy(false)
            }}
          >
            Cancel connection
          </button>
        </div>
      )}
      {failed && (
        <p role="alert">
          Couldn’t load or save calendars. Connect Google Calendar, then reload and try again.
        </p>
      )}
      {data && (
        <>
          <p className="text-sm text-text-tertiary">
            Read selected calendars. New events use{' '}
            {data.calendars.find((row) => row.primary)?.name ?? data.account_id}.
          </p>
          {data.calendars.map((calendar) => (
            <label
              key={calendar.id}
              className="flex min-h-11 cursor-pointer items-center gap-3 text-sm"
            >
              <input
                type="checkbox"
                checked={selected.includes(calendar.id)}
                disabled={busy || (!calendar.available && !selected.includes(calendar.id))}
                onChange={(event) => {
                  setSaved(false)
                  setSelected(
                    event.target.checked
                      ? [...selected, calendar.id]
                      : selected.filter((id) => id !== calendar.id)
                  )
                }}
              />
              {calendar.name || `${calendar.id} — No longer available`}
            </label>
          ))}
          <div className="flex gap-2">
            <button
              className="btn-ghost disabled:opacity-40"
              disabled={busy}
              onClick={() => {
                setSelected(data.selected_ids)
                setSaved(false)
              }}
            >
              Cancel
            </button>
            <button
              className="btn-primary px-4 py-2 disabled:opacity-40"
              disabled={busy || !selected.length}
              onClick={save}
            >
              Save
            </button>
          </div>
          {saved && <p role="status">Calendar selection saved</p>}
        </>
      )}
    </div>
  )
}
