import { useEffect, useState } from 'react'
import { StickyNote, Mail, Check, Loader2, ExternalLink, RefreshCw, Plug } from 'lucide-react'
import { omiApi } from '../../../lib/apiClient'
import { toast } from '../../../lib/toast'
import { extractNoteMemories } from '../../../lib/stickyNotesExtract'
import { runGoogleSync } from '../../../lib/googleSync'
import { useMemories } from '../../../hooks/useMemories'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import type { GoogleStatus } from '../../../../../shared/types'

const GOOGLE_ENABLED =
  import.meta.env.VITE_ENABLE_GOOGLE_INTEGRATION === '1' ||
  (import.meta.env.DEV && localStorage.getItem('omi.google.enabled') === '1')

const STICKY_NOTE_TAG = 'sticky_notes/import/note'
const STICKY_PROFILE_TAG = 'sticky_notes/import/profile'

type AppEntry = { id: string; name?: string; description?: string; image?: string | null; category?: string | null }

// Per-plugin config card matching macOS Settings → Integrations layout
function PluginCard({
  app,
  enabled,
  busy,
  onToggle
}: {
  app: AppEntry
  enabled: boolean
  busy: boolean
  onToggle: () => void
}): React.JSX.Element {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
      {app.image ? (
        <img
          src={app.image}
          alt=""
          className="mt-0.5 h-9 w-9 shrink-0 rounded-xl border border-white/10 object-cover"
          onError={(e) => { (e.target as HTMLImageElement).style.visibility = 'hidden' }}
        />
      ) : (
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
          <Plug className="h-4 w-4 text-white/40" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-white/90">{app.name ?? app.id}</p>
          {enabled && (
            <span className="flex items-center gap-1 rounded-full bg-green-500/15 px-1.5 py-0.5 text-[10px] font-medium text-green-400">
              <Check className="h-2.5 w-2.5" />
              Active
            </span>
          )}
        </div>
        {app.description && (
          <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-white/45">{app.description}</p>
        )}
      </div>
      <div className="shrink-0">
        <Toggle on={enabled} onChange={onToggle} disabled={busy} label={`${app.name ?? app.id} integration`} />
      </div>
    </div>
  )
}

export function IntegrationsTab(): React.JSX.Element {
  const { memories, refresh } = useMemories()

  // ── Installed plugins from marketplace ────────────────────────────────────
  const [plugins, setPlugins] = useState<AppEntry[]>([])
  const [pluginEnabled, setPluginEnabled] = useState<Set<string>>(new Set())
  const [pluginBusy, setPluginBusy] = useState<Set<string>>(new Set())
  const [pluginsLoading, setPluginsLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      omiApi.get<AppEntry[]>('/v1/apps', { params: { include_reviews: false } }),
      omiApi.get<string[]>('/v1/apps/enabled').catch(() => ({ data: [] as string[] }))
    ]).then(([appsRes, enabledRes]) => {
      const all = Array.isArray(appsRes.data) ? appsRes.data : []
      const enabledIds = Array.isArray(enabledRes.data) ? enabledRes.data : []
      setPlugins(all)
      setPluginEnabled(new Set(enabledIds))
    }).catch(() => {}).finally(() => setPluginsLoading(false))
  }, [])

  const togglePlugin = async (id: string): Promise<void> => {
    if (pluginBusy.has(id)) return
    setPluginBusy((s) => new Set(s).add(id))
    const wasOn = pluginEnabled.has(id)
    setPluginEnabled((s) => { const n = new Set(s); if (wasOn) n.delete(id); else n.add(id); return n })
    try {
      if (wasOn) {
        await omiApi.delete(`/v1/apps/${id}/enable`)
      } else {
        await omiApi.post(`/v1/apps/${id}/enable`)
      }
    } catch (e) {
      setPluginEnabled((s) => { const n = new Set(s); if (wasOn) n.add(id); else n.delete(id); return n })
      toast('Could not update plugin', { tone: 'error', body: (e as Error).message })
    } finally {
      setPluginBusy((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  // ── Sticky Notes ─────────────────────────────────────────────────────────
  const [stickyReading, setStickyReading] = useState(false)
  const [stickyImporting, setStickyImporting] = useState(false)
  const [stickyMemories, setStickyMemories] = useState<string[] | null>(null)
  const [stickyProfile, setStickyProfile] = useState('')

  const readSticky = async (): Promise<void> => {
    if (stickyReading || stickyImporting) return
    setStickyReading(true); setStickyMemories(null); setStickyProfile('')
    try {
      const result = await window.omi.readStickyNotes()
      if (!result.available) { toast('No Sticky Notes found on this PC', { tone: 'warn' }); return }
      if (result.error) { toast('Could not read Sticky Notes', { tone: 'error', body: result.error }); return }
      if (result.notes.length === 0) { toast('No note text to import', { tone: 'warn' }); return }
      const notesText = result.notes.map((n) => n.text).join('\n\n---\n\n')
      const { memories: list, profile } = await extractNoteMemories(notesText, memories.map((m) => m.content))
      setStickyMemories(list); setStickyProfile(profile)
      if (list.length === 0) toast('No new memories found in your notes', { tone: 'warn' })
    } catch (e) {
      toast('Could not read Sticky Notes', { tone: 'error', body: (e as Error).message })
    } finally {
      setStickyReading(false)
    }
  }

  const importSticky = async (): Promise<void> => {
    if (!stickyMemories?.length || stickyImporting) return
    setStickyImporting(true)
    let ok = 0; let failed = 0; let firstError = ''
    for (const content of stickyMemories) {
      try {
        await omiApi.post('/v3/memories', { content, tags: [STICKY_NOTE_TAG] })
        ok++
      } catch (e) {
        if (!firstError) firstError = (e as { response?: { data?: { detail?: string } }; message: string }).response?.data?.detail ?? (e as Error).message
        failed++
      }
    }
    if (stickyProfile.trim()) {
      try { await omiApi.post('/v3/memories', { content: stickyProfile.trim(), tags: [STICKY_PROFILE_TAG] }) } catch { /* best-effort */ }
    }
    setStickyImporting(false)
    toast(`Imported ${ok} memor${ok === 1 ? 'y' : 'ies'}${failed ? `, ${failed} failed` : ''}`, {
      tone: failed ? (ok ? 'warn' : 'error') : 'success', body: failed ? firstError : undefined
    })
    if (ok > 0) await refresh()
    if (!failed) { setStickyMemories(null); setStickyProfile('') }
  }

  // ── Google ───────────────────────────────────────────────────────────────
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
      if (out.errors.length > 0) toast('Sync finished with errors', { tone: 'warn', body: out.errors.join('; ') })
      else toast(`Synced — ${out.memoriesAdded} memor${out.memoriesAdded === 1 ? 'y' : 'ies'}, ${out.tasksAdded} task${out.tasksAdded === 1 ? '' : 's'}`, { tone: 'success' })
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
    } finally { setGoogleBusy(false) }
  }

  const disconnectGoogle = async (): Promise<void> => {
    if (googleBusy) return
    setGoogleBusy(true)
    try {
      setGoogleStatus(await window.omi.googleDisconnect())
      toast('Google disconnected', { tone: 'success' })
    } catch (e) {
      toast('Could not disconnect', { tone: 'error', body: (e as Error).message })
    } finally { setGoogleBusy(false) }
  }

  // Enabled plugins to show in the "Installed" section
  const installedPlugins = plugins.filter((p) => pluginEnabled.has(p.id))
  const availablePlugins = plugins.filter((p) => !pluginEnabled.has(p.id)).slice(0, 6)

  return (
    <>
      {/* ── Installed plugins ─────────────────────────────────────────────── */}
      {!pluginsLoading && installedPlugins.length > 0 && (
        <SettingRow
          icon={Check}
          dot="on"
          title="Active plugins"
          subtitle={`${installedPlugins.length} plugin${installedPlugins.length !== 1 ? 's' : ''} enabled — they run when Omi processes new conversations.`}
          keywords="plugin integration app active enabled"
        >
          <div className="space-y-2">
            {installedPlugins.map((p) => (
              <PluginCard
                key={p.id}
                app={p}
                enabled={true}
                busy={pluginBusy.has(p.id)}
                onToggle={() => void togglePlugin(p.id)}
              />
            ))}
          </div>
        </SettingRow>
      )}

      {/* ── Discover plugins ──────────────────────────────────────────────── */}
      {!pluginsLoading && availablePlugins.length > 0 && (
        <SettingRow
          icon={Plug}
          title="Available plugins"
          subtitle="Enable plugins to extend Omi's capabilities — summaries, action extraction, CRM sync, and more."
          keywords="plugin app marketplace discover install"
        >
          <div className="space-y-2">
            {availablePlugins.map((p) => (
              <PluginCard
                key={p.id}
                app={p}
                enabled={false}
                busy={pluginBusy.has(p.id)}
                onToggle={() => void togglePlugin(p.id)}
              />
            ))}
            <button
              onClick={() => { window.location.hash = '#/apps' }}
              className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors pt-1"
            >
              <ExternalLink className="h-3 w-3" />
              Browse all plugins in the App Store
            </button>
          </div>
        </SettingRow>
      )}

      {pluginsLoading && (
        <SettingRow
          icon={Loader2}
          title="Loading plugins…"
          subtitle=""
          keywords="plugin loading"
          control={<Loader2 className="h-4 w-4 animate-spin text-white/30" />}
        />
      )}

      {/* ── Windows Sticky Notes ──────────────────────────────────────────── */}
      <SettingRow
        icon={StickyNote}
        title="Windows Sticky Notes"
        subtitle="Reads your Sticky Notes locally and saves durable facts as memories. Your notes are never uploaded — only the synthesized facts."
        keywords="sticky notes import integration"
        control={
          <div className="flex items-center gap-2">
            <button onClick={readSticky} disabled={stickyReading || stickyImporting} className="btn-ghost disabled:opacity-40">
              {stickyReading ? 'Reading…' : 'Read notes'}
            </button>
            {stickyMemories && stickyMemories.length > 0 && (
              <button onClick={importSticky} disabled={stickyImporting} className="btn-primary px-4 py-2 disabled:opacity-40">
                {stickyImporting ? 'Importing…' : `Import ${stickyMemories.length} memor${stickyMemories.length === 1 ? 'y' : 'ies'}`}
              </button>
            )}
          </div>
        }
      >
        {stickyProfile && (
          <p className="glass-subtle mb-2 rounded-lg px-4 py-3 text-sm italic text-text-tertiary">{stickyProfile}</p>
        )}
        {stickyMemories && stickyMemories.length > 0 && (
          <ul className="glass-subtle max-h-40 overflow-y-auto rounded-lg px-4 py-3 text-sm text-text-tertiary">
            {stickyMemories.map((m, i) => <li key={i} className="py-0.5">• {m}</li>)}
          </ul>
        )}
      </SettingRow>

      {/* ── Google ────────────────────────────────────────────────────────── */}
      {GOOGLE_ENABLED && (
        <SettingRow
          icon={Mail}
          dot={googleStatus.connected ? 'on' : 'off'}
          title="Google (Gmail + Calendar)"
          subtitle={
            googleStatus.connected
              ? `Connected${googleStatus.email ? ` as ${googleStatus.email}` : ''}${googleStatus.lastSyncAt ? ` · last sync ${new Date(googleStatus.lastSyncAt).toLocaleString()}` : ''}`
              : 'Turn recent email (subject/sender only) into memories and upcoming events into tasks.'
          }
          keywords="google gmail calendar sync integration"
          control={
            googleStatus.connected ? (
              <div className="flex items-center gap-2">
                <button onClick={runSync} disabled={googleSyncing} className="btn-primary px-4 py-2 disabled:opacity-40">
                  {googleSyncing ? <><RefreshCw className="inline h-3 w-3 animate-spin mr-1" />Syncing…</> : 'Sync now'}
                </button>
                <button onClick={disconnectGoogle} disabled={googleBusy} className="btn-ghost disabled:opacity-40">Disconnect</button>
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
