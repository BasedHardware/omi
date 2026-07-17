import { useEffect, useState } from 'react'
import { StickyNote, Mail, Inbox } from 'lucide-react'
import { toast } from '../../../lib/toast'
import { readAndExtractStickyNotes, importStickyMemories } from '../../../lib/stickyNotesImport'
import { toastImportTally } from '../../../lib/importToast'
import { useMemories } from '../../../hooks/useMemories'
import { useGoogleConnection } from '../../../hooks/useGoogleConnection'
import { GMAIL_SESSION_ENABLED } from '../../../lib/gmailSessionFeatureFlag'
import { SettingRow } from '../SettingRow'
import type { GmailSessionStatus } from '../../../../../shared/types'

export function IntegrationsTab(): React.JSX.Element {
  const { memories, refresh } = useMemories()

  // --- Sticky Notes ---
  const [stickyReading, setStickyReading] = useState(false)
  const [stickyImporting, setStickyImporting] = useState(false)
  const [stickyMemories, setStickyMemories] = useState<string[] | null>(null)
  const [stickyProfile, setStickyProfile] = useState('')

  const readSticky = async (): Promise<void> => {
    if (stickyReading || stickyImporting) return
    setStickyReading(true)
    setStickyMemories(null)
    setStickyProfile('')
    try {
      const outcome = await readAndExtractStickyNotes(memories.map((m) => m.content))
      if (outcome.status === 'unavailable')
        toast('No Sticky Notes found on this PC', { tone: 'warn' })
      else if (outcome.status === 'error')
        toast('Could not read Sticky Notes', { tone: 'error', body: outcome.error })
      else if (outcome.status === 'empty')
        toast(
          outcome.reason === 'no-notes'
            ? 'No note text to import'
            : 'No new memories found in your notes',
          { tone: 'warn' }
        )
      else {
        setStickyMemories(outcome.memories)
        setStickyProfile(outcome.profile)
      }
    } catch (e) {
      toast('Could not read Sticky Notes', { tone: 'error', body: (e as Error).message })
    } finally {
      setStickyReading(false)
    }
  }

  const importSticky = async (): Promise<void> => {
    if (!stickyMemories || stickyMemories.length === 0 || stickyImporting) return
    setStickyImporting(true)
    const tally = await importStickyMemories(stickyMemories, stickyProfile)
    setStickyImporting(false)
    toastImportTally(tally)
    if (tally.ok > 0) await refresh()
    if (!tally.failed) {
      setStickyMemories(null)
      setStickyProfile('')
    }
  }

  // --- Google --- (client-side Gmail lane; shared with the Hub Email card, incl.
  // the sync-on-connect + 15-min background resync, via the singleton hook.)
  const {
    googleEnabled,
    status: googleStatus,
    connect: connectGoogle,
    disconnect: disconnectGoogle,
    syncNow: runSync,
    busy: googleBusy,
    syncing: googleSyncing
  } = useGoogleConnection()

  // --- Gmail (session): Option B. Sign into Google once inside an Omi-owned window;
  // we replay Gmail's web endpoints against that persisted session (no OAuth scopes). ---
  const [gmailStatus, setGmailStatus] = useState<GmailSessionStatus>({ connected: false })
  const [gmailBusy, setGmailBusy] = useState(false)
  const [gmailFetching, setGmailFetching] = useState(false)

  useEffect(() => {
    if (!GMAIL_SESSION_ENABLED) return
    window.omi
      .gmailSessionStatus()
      .then(setGmailStatus)
      .catch(() => {})
  }, [])

  const connectGmail = async (): Promise<void> => {
    if (gmailBusy) return
    setGmailBusy(true)
    try {
      const next = await window.omi.gmailSessionConnect()
      setGmailStatus(next)
      if (next.connected) toast('Gmail connected', { tone: 'success' })
      else if (next.message) toast('Gmail not connected', { tone: 'warn', body: next.message })
    } catch (e) {
      toast('Could not connect Gmail', { tone: 'error', body: (e as Error).message })
    } finally {
      setGmailBusy(false)
    }
  }

  const fetchGmail = async (): Promise<void> => {
    if (gmailFetching) return
    setGmailFetching(true)
    try {
      const res = await window.omi.gmailSessionFetch('newer_than:7d', 25)
      if (res.ok) {
        toast(`Read ${res.emails.length} recent email${res.emails.length === 1 ? '' : 's'}`, {
          tone: 'success'
        })
      } else {
        toast('Could not read Gmail', { tone: 'warn', body: res.error })
        // A stale/expired session flips the row back to a "Connect" prompt.
        setGmailStatus(await window.omi.gmailSessionStatus())
      }
    } catch (e) {
      toast('Could not read Gmail', { tone: 'error', body: (e as Error).message })
    } finally {
      setGmailFetching(false)
    }
  }

  const disconnectGmail = async (): Promise<void> => {
    if (gmailBusy) return
    setGmailBusy(true)
    try {
      setGmailStatus(await window.omi.gmailSessionDisconnect())
      toast('Gmail disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setGmailBusy(false)
    }
  }

  return (
    <>
      <SettingRow
        icon={StickyNote}
        title="Windows Sticky Notes"
        subtitle="Reads your Sticky Notes locally and saves durable facts as memories. Your notes are never uploaded — only the synthesized facts."
        keywords="sticky notes import integration"
        control={
          <div className="flex items-center gap-2">
            <button
              onClick={readSticky}
              disabled={stickyReading || stickyImporting}
              className="btn-ghost disabled:opacity-40"
            >
              {stickyReading ? 'Reading…' : 'Read notes'}
            </button>
            {stickyMemories && stickyMemories.length > 0 && (
              <button
                onClick={importSticky}
                disabled={stickyImporting}
                className="btn-primary px-4 py-2 disabled:opacity-40"
              >
                {stickyImporting
                  ? 'Importing…'
                  : `Import ${stickyMemories.length} memor${stickyMemories.length === 1 ? 'y' : 'ies'}`}
              </button>
            )}
          </div>
        }
      >
        {stickyProfile && (
          <p className="glass-subtle mb-2 rounded-lg px-4 py-3 text-sm italic text-text-tertiary">
            {stickyProfile}
          </p>
        )}
        {stickyMemories && stickyMemories.length > 0 && (
          <ul className="glass-subtle max-h-40 overflow-y-auto rounded-lg px-4 py-3 text-sm text-text-tertiary">
            {stickyMemories.map((m, i) => (
              <li key={i} className="py-0.5">
                • {m}
              </li>
            ))}
          </ul>
        )}
      </SettingRow>

      {googleEnabled && (
        <SettingRow
          icon={Mail}
          dot={googleStatus.connected ? 'on' : 'off'}
          title="Google (Gmail + Calendar)"
          subtitle={
            googleStatus.connected
              ? `Connected${googleStatus.email ? ` as ${googleStatus.email}` : ''}${
                  googleStatus.lastSyncAt
                    ? ` · last sync ${new Date(googleStatus.lastSyncAt).toLocaleString()}`
                    : ''
                }`
              : 'Turn recent email (subject/sender only) into memories and upcoming events into tasks.'
          }
          keywords="google gmail calendar sync integration"
          control={
            googleStatus.connected ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={runSync}
                  disabled={googleSyncing}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {googleSyncing ? 'Syncing…' : 'Sync now'}
                </button>
                <button
                  onClick={disconnectGoogle}
                  disabled={googleBusy}
                  className="btn-ghost disabled:opacity-40"
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <button
                onClick={connectGoogle}
                disabled={googleBusy}
                className="btn-ghost disabled:opacity-40"
              >
                {googleBusy ? 'Connecting…' : 'Connect'}
              </button>
            )
          }
        />
      )}

      {GMAIL_SESSION_ENABLED && (
        <SettingRow
          icon={Inbox}
          dot={gmailStatus.connected ? 'on' : 'off'}
          title="Gmail (session)"
          subtitle={
            gmailStatus.connected
              ? 'Connected — reads recent mail through your signed-in Google session. No OAuth scopes; sign-in stays inside Omi.'
              : gmailStatus.message ||
                'Sign into Google once inside Omi, then read recent mail without restricted-scope OAuth.'
          }
          keywords="gmail session email inbox connect integration"
          control={
            gmailStatus.connected ? (
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchGmail}
                  disabled={gmailFetching}
                  className="btn-primary px-4 py-2 disabled:opacity-40"
                >
                  {gmailFetching ? 'Reading…' : 'Fetch recent'}
                </button>
                <button
                  onClick={disconnectGmail}
                  disabled={gmailBusy}
                  className="btn-ghost disabled:opacity-40"
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <button
                onClick={connectGmail}
                disabled={gmailBusy}
                className="btn-ghost disabled:opacity-40"
              >
                {gmailBusy ? 'Connecting…' : 'Connect'}
              </button>
            )
          }
        />
      )}
    </>
  )
}
