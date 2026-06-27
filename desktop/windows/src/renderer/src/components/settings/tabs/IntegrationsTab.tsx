import { useEffect, useState } from 'react'
import { StickyNote, Mail } from 'lucide-react'
import { omiApi } from '../../../lib/apiClient'
import { toast } from '../../../lib/toast'
import { extractNoteMemories } from '../../../lib/stickyNotesExtract'
import { runGoogleSync } from '../../../lib/googleSync'
import { useMemories } from '../../../hooks/useMemories'
import { SettingRow } from '../SettingRow'
import type { GoogleStatus } from '../../../../../shared/types'

const GOOGLE_ENABLED =
  import.meta.env.VITE_ENABLE_GOOGLE_INTEGRATION === '1' ||
  (import.meta.env.DEV && localStorage.getItem('omi.google.enabled') === '1')

const STICKY_NOTE_TAG = 'sticky_notes/import/note'
const STICKY_PROFILE_TAG = 'sticky_notes/import/profile'

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
      const result = await window.omi.readStickyNotes()
      if (!result.available) {
        toast('No Sticky Notes found on this PC', { tone: 'warn' })
        return
      }
      if (result.error) {
        toast('Could not read Sticky Notes', { tone: 'error', body: result.error })
        return
      }
      if (result.notes.length === 0) {
        toast('No note text to import', { tone: 'warn' })
        return
      }
      const notesText = result.notes.map((n) => n.text).join('\n\n---\n\n')
      const existing = memories.map((m) => m.content)
      const { memories: list, profile } = await extractNoteMemories(notesText, existing)
      setStickyMemories(list)
      setStickyProfile(profile)
      if (list.length === 0) toast('No new memories found in your notes', { tone: 'warn' })
    } catch (e) {
      toast('Could not read Sticky Notes', { tone: 'error', body: (e as Error).message })
    } finally {
      setStickyReading(false)
    }
  }

  const importSticky = async (): Promise<void> => {
    if (!stickyMemories || stickyMemories.length === 0 || stickyImporting) return
    setStickyImporting(true)
    let ok = 0
    let failed = 0
    let firstError = ''
    for (const content of stickyMemories) {
      try {
        await omiApi.post('/v3/memories', { content, tags: [STICKY_NOTE_TAG] })
        ok++
      } catch (e) {
        const msg =
          (e as { response?: { data?: { detail?: string } }; message: string }).response?.data
            ?.detail ?? (e as Error).message
        if (!firstError) firstError = msg
        failed++
      }
    }
    if (stickyProfile.trim()) {
      try {
        await omiApi.post('/v3/memories', { content: stickyProfile.trim(), tags: [STICKY_PROFILE_TAG] })
      } catch {
        /* profile is best-effort */
      }
    }
    setStickyImporting(false)
    toast(`Imported ${ok} memor${ok === 1 ? 'y' : 'ies'}${failed ? `, ${failed} failed` : ''}`, {
      tone: failed ? (ok ? 'warn' : 'error') : 'success',
      body: failed ? firstError : undefined
    })
    if (ok > 0) await refresh()
    if (!failed) {
      setStickyMemories(null)
      setStickyProfile('')
    }
  }

  // --- Google ---
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus>({ connected: false })
  const [googleBusy, setGoogleBusy] = useState(false)
  const [googleSyncing, setGoogleSyncing] = useState(false)

  useEffect(() => {
    if (!GOOGLE_ENABLED) return
    window.omi.googleStatus().then(setGoogleStatus).catch(() => {})
  }, [])

  const runSync = async (): Promise<void> => {
    if (googleSyncing) return
    setGoogleSyncing(true)
    try {
      const out = await runGoogleSync(memories.map((m) => m.content))
      if (out.errors.length > 0) {
        toast('Sync finished with errors', { tone: 'warn', body: out.errors.join('; ') })
      } else {
        toast(
          `Synced — ${out.memoriesAdded} memor${out.memoriesAdded === 1 ? 'y' : 'ies'}, ${out.tasksAdded} task${out.tasksAdded === 1 ? '' : 's'}`,
          { tone: 'success' }
        )
      }
      if (out.memoriesAdded > 0) await refresh()
      await window.omi.googleStatus().then(setGoogleStatus)
    } catch (e) {
      toast('Google sync failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setGoogleSyncing(false)
    }
  }

  useEffect(() => {
    if (!GOOGLE_ENABLED || !googleStatus.connected) return
    void runSync()
    const id = setInterval(() => void runSync(), 15 * 60 * 1000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [googleStatus.connected])

  const connectGoogle = async (): Promise<void> => {
    if (googleBusy) return
    setGoogleBusy(true)
    try {
      const status = await window.omi.googleConnect()
      setGoogleStatus(status)
      if (status.connected) toast('Google connected', { tone: 'success', body: status.email })
    } catch (e) {
      toast('Could not connect Google', { tone: 'error', body: (e as Error).message })
    } finally {
      setGoogleBusy(false)
    }
  }

  const disconnectGoogle = async (): Promise<void> => {
    if (googleBusy) return
    setGoogleBusy(true)
    try {
      setGoogleStatus(await window.omi.googleDisconnect())
      toast('Google disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally {
      setGoogleBusy(false)
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
              <li key={i} className="py-0.5">• {m}</li>
            ))}
          </ul>
        )}
      </SettingRow>

      {GOOGLE_ENABLED && (
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
                <button onClick={disconnectGoogle} disabled={googleBusy} className="btn-ghost disabled:opacity-40">
                  Disconnect
                </button>
              </div>
            ) : (
              <button onClick={connectGoogle} disabled={googleBusy} className="btn-ghost disabled:opacity-40">
                {googleBusy ? 'Connecting…' : 'Connect'}
              </button>
            )
          }
        />
      )}
    </>
  )
}
