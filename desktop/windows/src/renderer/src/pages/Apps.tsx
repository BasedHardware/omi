import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  Check,
  Cloud,
  Copy,
  Database,
  Download,
  ExternalLink,
  FileText,
  FolderSearch,
  LayoutGrid,
  Loader2,
  Mail,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Star,
  StickyNote,
  Upload,
  X
} from 'lucide-react'
import { omiApi } from '../lib/apiClient'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { McpConnectorSetup } from '../components/connectors/McpConnectorSetup'
import { extractMemories, normalize, type MemorySource } from '../lib/memoryExtract'
import { extractNoteMemories } from '../lib/stickyNotesExtract'
import { runGoogleSync } from '../lib/googleSync'
import { fetchAllMemories } from '../lib/memoriesBulk'
import { buildLocalGraph } from '../lib/kgSynthesis'
import { useMemories, type Memory } from '../hooks/useMemories'
import {
  memoryImportApp,
  readMemoryImportStats,
  recordMemoryImport,
  type MemoryImportStatsBySource
} from '../lib/memoryImportFlow'
import type {
  ExportMemory,
  FileIndexStatus,
  GoogleStatus,
  MemoryExportResult
} from '../../../shared/types'

type AppEntry = {
  id: string
  name?: string
  description?: string
  image?: string | null
  author?: string | null
  category?: string | null
  rating_avg?: number | null
  installs?: number | null
  is_paid?: boolean
  price?: number | null
}

type StatusKind = 'connected' | 'optional' | 'not-configured' | 'working' | 'loading' | 'error'
type ExportTarget = 'obsidian' | 'file' | 'notion'
type StickyProbe = { available: boolean; count: number; error?: string }
type StatusMessage = { tone: 'info' | 'success' | 'warn' | 'error'; text: string } | null

const GOOGLE_CONFIGURED =
  import.meta.env.VITE_ENABLE_GOOGLE_INTEGRATION === '1' ||
  (import.meta.env.DEV && localStorage.getItem('omi.google.enabled') === '1')

const STICKY_NOTE_TAG = 'sticky_notes/import/note'
const STICKY_PROFILE_TAG = 'sticky_notes/import/profile'

function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count.toLocaleString()} ${count === 1 ? singular : plural}`
}

function formatDateTime(ts?: number | null): string {
  if (!ts) return 'Never'
  return new Date(ts).toLocaleString()
}

function errorMessage(error: unknown): string {
  return (
    (error as { response?: { data?: { detail?: string }; status?: number }; message?: string })
      .response?.data?.detail ??
    (error as { response?: { status?: number } }).response?.status?.toString() ??
    (error as Error).message
  )
}

function toExportMemories(memories: Memory[]): ExportMemory[] {
  return memories.map((m) => ({
    content: m.content,
    category: m.category ?? null,
    createdAt: m.created_at
  }))
}

// Turns raw API categories like "chat-assistants" into "Chat Assistants".
function formatCategory(raw: string): string {
  return raw
    .replace(/[-_]+/g, ' ')
    .trim()
    .split(/\s+/)
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(' ')
}

function statusLabel(kind: StatusKind): string {
  if (kind === 'connected') return 'Connected'
  if (kind === 'not-configured') return 'Not configured'
  if (kind === 'working') return 'Working'
  if (kind === 'loading') return 'Checking'
  if (kind === 'error') return 'Needs attention'
  return 'Optional'
}

function StatusBadge({ kind }: { kind: StatusKind }): React.JSX.Element {
  const dot =
    kind === 'connected'
      ? 'bg-emerald-300'
      : kind === 'working' || kind === 'loading'
        ? 'bg-sky-300'
        : kind === 'error'
          ? 'bg-red-300'
          : kind === 'not-configured'
            ? 'bg-white/25'
            : 'bg-amber-200'
  return (
    <span className="badge gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {statusLabel(kind)}
    </span>
  )
}

function IntegrationCard({
  icon: Icon,
  title,
  description,
  status,
  statusText,
  children
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  description: string
  status: StatusKind
  statusText: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <section className="surface-card flex min-h-[20rem] flex-col p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-black/20">
            <Icon className="h-5 w-5 text-white/70" />
          </div>
          <div className="min-w-0">
            <h2 className="font-display text-base font-semibold text-white">{title}</h2>
            <p className="mt-1 text-xs leading-relaxed text-white/55">{description}</p>
          </div>
        </div>
        <StatusBadge kind={status} />
      </div>
      <p className="mb-4 text-xs text-white/45">{statusText}</p>
      <div className="mt-auto space-y-3">{children}</div>
    </section>
  )
}

function InlineStatus({ message }: { message: StatusMessage }): React.JSX.Element | null {
  if (!message) return null
  const tone =
    message.tone === 'success'
      ? 'text-emerald-200/90'
      : message.tone === 'warn'
        ? 'text-amber-100/90'
        : message.tone === 'error'
          ? 'text-red-200/90'
          : 'text-white/60'
  return (
    <div className={`glass-subtle px-4 py-3 text-xs leading-relaxed ${tone}`}>{message.text}</div>
  )
}

function MemoryPreview({
  profile,
  memories
}: {
  profile?: string
  memories: string[] | null
}): React.JSX.Element | null {
  if (!profile && (!memories || memories.length === 0)) return null
  return (
    <div className="glass-subtle max-h-44 overflow-y-auto px-4 py-3 text-xs leading-relaxed text-white/60">
      {profile && <p className="mb-2 italic text-white/70">{profile}</p>}
      {memories && memories.length > 0 && (
        <ul className="space-y-1">
          {memories.map((memory, index) => (
            <li key={`${index}-${memory}`} className="flex gap-2">
              <span className="text-white/35">-</span>
              <span>{memory}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SectionTitle({
  title,
  subtitle
}: {
  title: string
  subtitle?: string
}): React.JSX.Element {
  return (
    <div>
      <h2 className="font-display text-lg font-semibold text-white">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-white/50">{subtitle}</p>}
    </div>
  )
}

function AppCard({
  app,
  isOn,
  isBusy,
  onToggle
}: {
  app: AppEntry
  isOn: boolean
  isBusy: boolean
  onToggle: (a: AppEntry) => void
}): React.JSX.Element {
  return (
    <div className="surface-card flex flex-col p-5 animate-fade-in">
      <div className="mb-3 flex items-start gap-3">
        {app.image ? (
          <img
            src={app.image}
            alt=""
            className="h-12 w-12 shrink-0 rounded-2xl border border-white/10 object-cover"
            onError={(e) => {
              ;(e.target as HTMLImageElement).style.visibility = 'hidden'
            }}
          />
        ) : (
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
            <LayoutGrid className="h-5 w-5 text-white/60" />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="font-display font-semibold text-white/95">{app.name}</div>
          {app.author && <div className="text-[11px] text-white/45">{app.author}</div>}
        </div>
      </div>
      <p className="mb-4 line-clamp-3 flex-1 text-xs leading-relaxed text-white/65">
        {app.description}
      </p>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[11px] text-white/45">
          {app.rating_avg ? (
            <span className="flex items-center gap-1">
              <Star className="h-3 w-3" />
              {app.rating_avg.toFixed(1)}
            </span>
          ) : null}
          {app.category && <span className="badge">{formatCategory(app.category)}</span>}
        </div>
        <button
          onClick={() => onToggle(app)}
          disabled={isBusy}
          className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
            isOn
              ? 'border-white/20 bg-white/10 text-white'
              : 'border-white/15 bg-transparent text-white/70 hover:bg-white/5 hover:text-white'
          } ${isBusy ? 'opacity-60' : ''}`}
        >
          {isBusy ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : isOn ? (
            <Check className="h-3 w-3" />
          ) : (
            <Plus className="h-3 w-3" />
          )}
          {isOn ? 'Installed' : 'Install'}
        </button>
      </div>
    </div>
  )
}

export function Apps(): React.JSX.Element {
  const {
    memories,
    loading: memoriesLoading,
    error: memoriesError,
    refresh: refreshMemories
  } = useMemories()

  const [apps, setApps] = useState<AppEntry[]>([])
  const [enabled, setEnabled] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [tab, setTab] = useState<'all' | 'installed'>('all')
  const [busy, setBusy] = useState<Set<string>>(new Set())
  const [selectedCats, setSelectedCats] = useState<Set<string>>(new Set())
  const [filterOpen, setFilterOpen] = useState(false)
  const filterRef = useRef<HTMLDivElement>(null)

  const [mcpHasKey, setMcpHasKey] = useState<boolean | null>(null)

  const [googleStatus, setGoogleStatus] = useState<GoogleStatus>({ connected: false })
  const [googleLoading, setGoogleLoading] = useState(GOOGLE_CONFIGURED)
  const [googleBusy, setGoogleBusy] = useState(false)
  const [googleSyncing, setGoogleSyncing] = useState(false)
  const [googleMessage, setGoogleMessage] = useState<StatusMessage>(null)

  const [stickyProbe, setStickyProbe] = useState<StickyProbe | null>(null)
  const [stickyLoading, setStickyLoading] = useState(true)
  const [stickyReading, setStickyReading] = useState(false)
  const [stickyImporting, setStickyImporting] = useState(false)
  const [stickyMemories, setStickyMemories] = useState<string[] | null>(null)
  const [stickyProfile, setStickyProfile] = useState('')
  const [stickyMessage, setStickyMessage] = useState<StatusMessage>(null)

  const [fileIndex, setFileIndex] = useState<FileIndexStatus | null>(null)
  const [fileIndexLoading, setFileIndexLoading] = useState(true)
  const [fileScanning, setFileScanning] = useState(false)
  const [fileMessage, setFileMessage] = useState<StatusMessage>(null)

  const [dump, setDump] = useState('')
  const [source, setSource] = useState<MemorySource>('chatgpt')
  const [parsed, setParsed] = useState<string[] | null>(null)
  const [profile, setProfile] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importMessage, setImportMessage] = useState<StatusMessage>(null)
  const [importStats, setImportStats] = useState<MemoryImportStatsBySource>(() =>
    readMemoryImportStats()
  )

  const [notionToken, setNotionToken] = useState('')
  const [notionPage, setNotionPage] = useState('')
  const [exporting, setExporting] = useState<ExportTarget | null>(null)
  const [exportMessage, setExportMessage] = useState<StatusMessage>(null)

  const selectedImportApp = memoryImportApp(source)
  const selectedImportStats = importStats[source]

  const load = async (): Promise<void> => {
    setError(null)
    try {
      const [appsRes, enabledRes] = await Promise.all([
        omiApi.get<AppEntry[]>('/v1/apps', { params: { include_reviews: false } }),
        omiApi.get<string[]>('/v1/apps/enabled').catch(() => ({ data: [] as string[] }))
      ])
      setApps(Array.isArray(appsRes.data) ? appsRes.data : [])
      setEnabled(new Set(Array.isArray(enabledRes.data) ? enabledRes.data : []))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    let cancelled = false
    window.omi
      .readStickyNotes()
      .then((result) => {
        if (cancelled) return
        setStickyProbe({
          available: result.available,
          count: result.notes.length,
          error: result.error
        })
      })
      .catch((probeError) => {
        if (!cancelled) {
          setStickyProbe({ available: false, count: 0, error: (probeError as Error).message })
        }
      })
      .finally(() => {
        if (!cancelled) setStickyLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!GOOGLE_CONFIGURED) {
      setGoogleLoading(false)
      return
    }
    let cancelled = false
    window.omi
      .googleStatus()
      .then((status) => {
        if (!cancelled) setGoogleStatus(status)
      })
      .catch((statusError) => {
        if (!cancelled) {
          setGoogleMessage({
            tone: 'error',
            text: `Could not check Google: ${errorMessage(statusError)}`
          })
        }
      })
      .finally(() => {
        if (!cancelled) setGoogleLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    window.omi
      .indexFilesStatus()
      .then((status) => {
        if (!cancelled) setFileIndex(status)
      })
      .catch((statusError) => {
        if (!cancelled)
          setFileMessage({
            tone: 'error',
            text: `Could not check local files: ${errorMessage(statusError)}`
          })
      })
      .finally(() => {
        if (!cancelled) setFileIndexLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Debounce search so filtering doesn't run on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 500)
    return () => clearTimeout(t)
  }, [query])

  // Close the filter dropdown when clicking outside of it.
  useEffect(() => {
    if (!filterOpen) return
    const onClick = (e: MouseEvent): void => {
      if (filterRef.current && !filterRef.current.contains(e.target as Node)) {
        setFilterOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [filterOpen])

  const onRefresh = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    await Promise.all([
      load(),
      refreshMemories().catch(() => undefined),
      window.omi
        .indexFilesStatus()
        .then(setFileIndex)
        .catch(() => undefined),
      GOOGLE_CONFIGURED
        ? window.omi
            .googleStatus()
            .then(setGoogleStatus)
            .catch(() => undefined)
        : Promise.resolve()
    ])
    setRefreshing(false)
  }

  const toggle = async (a: AppEntry): Promise<void> => {
    if (busy.has(a.id)) return
    setBusy((s) => new Set(s).add(a.id))
    const wasEnabled = enabled.has(a.id)
    // Optimistic
    setEnabled((s) => {
      const next = new Set(s)
      if (wasEnabled) next.delete(a.id)
      else next.add(a.id)
      return next
    })
    try {
      if (wasEnabled) {
        await omiApi.post('/v1/apps/disable', null, { params: { app_id: a.id } })
      } else {
        await omiApi.post('/v1/apps/enable', null, { params: { app_id: a.id } })
      }
    } catch (e) {
      console.error('Toggle app failed:', e)
      // Revert
      setEnabled((s) => {
        const next = new Set(s)
        if (wasEnabled) next.add(a.id)
        else next.delete(a.id)
        return next
      })
    } finally {
      setBusy((s) => {
        const next = new Set(s)
        next.delete(a.id)
        return next
      })
    }
  }

  const connectGoogle = async (): Promise<void> => {
    if (googleBusy || !GOOGLE_CONFIGURED) return
    setGoogleBusy(true)
    setGoogleMessage({ tone: 'info', text: 'Opening Google authorization...' })
    try {
      const status = await window.omi.googleConnect()
      setGoogleStatus(status)
      setGoogleMessage({
        tone: status.connected ? 'success' : 'warn',
        text: status.connected
          ? `Google connected${status.email ? ` as ${status.email}` : ''}.`
          : 'Google did not return a connected account.'
      })
    } catch (connectError) {
      setGoogleMessage({
        tone: 'error',
        text: `Could not connect Google: ${errorMessage(connectError)}`
      })
    } finally {
      setGoogleBusy(false)
    }
  }

  const disconnectGoogle = async (): Promise<void> => {
    if (googleBusy || !GOOGLE_CONFIGURED) return
    setGoogleBusy(true)
    setGoogleMessage({ tone: 'info', text: 'Disconnecting Google...' })
    try {
      const status = await window.omi.googleDisconnect()
      setGoogleStatus(status)
      setGoogleMessage({ tone: 'success', text: 'Google disconnected.' })
    } catch (disconnectError) {
      setGoogleMessage({
        tone: 'error',
        text: `Could not disconnect Google: ${errorMessage(disconnectError)}`
      })
    } finally {
      setGoogleBusy(false)
    }
  }

  const syncGoogle = async (): Promise<void> => {
    if (googleSyncing || !GOOGLE_CONFIGURED || !googleStatus.connected) return
    setGoogleSyncing(true)
    setGoogleMessage({ tone: 'info', text: 'Syncing Gmail and Calendar...' })
    try {
      const out = await runGoogleSync(memories.map((m) => m.content))
      if (out.memoriesAdded > 0) await refreshMemories()
      const status = await window.omi.googleStatus()
      setGoogleStatus(status)
      setGoogleMessage({
        tone: out.errors.length > 0 ? 'warn' : 'success',
        text:
          out.errors.length > 0
            ? `Sync finished with errors: ${out.errors.join('; ')}`
            : `Synced ${pluralize(out.memoriesAdded, 'memory', 'memories')} and ${pluralize(out.tasksAdded, 'task')}.`
      })
    } catch (syncError) {
      setGoogleMessage({ tone: 'error', text: `Google sync failed: ${errorMessage(syncError)}` })
    } finally {
      setGoogleSyncing(false)
    }
  }

  const readSticky = async (): Promise<void> => {
    if (stickyReading || stickyImporting) return
    setStickyReading(true)
    setStickyMemories(null)
    setStickyProfile('')
    setStickyMessage({ tone: 'info', text: 'Reading Sticky Notes locally...' })
    try {
      const result = await window.omi.readStickyNotes()
      setStickyProbe({
        available: result.available,
        count: result.notes.length,
        error: result.error
      })
      if (!result.available) {
        setStickyMessage({ tone: 'warn', text: 'No Sticky Notes database was found on this PC.' })
        return
      }
      if (result.error) {
        setStickyMessage({ tone: 'error', text: `Could not read Sticky Notes: ${result.error}` })
        return
      }
      if (result.notes.length === 0) {
        setStickyMessage({
          tone: 'warn',
          text: 'Sticky Notes is available, but no readable note text was found.'
        })
        return
      }
      const notesText = result.notes.map((n) => n.text).join('\n\n---\n\n')
      const { memories: list, profile: stickySummary } = await extractNoteMemories(
        notesText,
        memories.map((m) => m.content)
      )
      setStickyMemories(list)
      setStickyProfile(stickySummary)
      setStickyMessage({
        tone: list.length > 0 ? 'success' : 'warn',
        text:
          list.length > 0
            ? `Found ${pluralize(list.length, 'new memory', 'new memories')} from ${pluralize(result.notes.length, 'note')}.`
            : 'No new durable memories were found in Sticky Notes.'
      })
    } catch (readError) {
      setStickyMessage({
        tone: 'error',
        text: `Could not read Sticky Notes: ${errorMessage(readError)}`
      })
    } finally {
      setStickyReading(false)
    }
  }

  const importSticky = async (): Promise<void> => {
    if (!stickyMemories || stickyMemories.length === 0 || stickyImporting) return
    setStickyImporting(true)
    setStickyMessage({
      tone: 'info',
      text: `Importing ${pluralize(stickyMemories.length, 'memory', 'memories')}...`
    })
    let ok = 0
    let failed = 0
    let firstError = ''
    for (const content of stickyMemories) {
      try {
        await omiApi.post('/v3/memories', { content, tags: [STICKY_NOTE_TAG] })
        ok++
      } catch (importError) {
        if (!firstError) firstError = errorMessage(importError)
        failed++
      }
    }
    if (stickyProfile.trim()) {
      try {
        await omiApi.post('/v3/memories', {
          content: stickyProfile.trim(),
          tags: [STICKY_PROFILE_TAG]
        })
      } catch {
        /* profile summary is best-effort */
      }
    }
    setStickyImporting(false)
    setStickyMessage({
      tone: failed ? (ok ? 'warn' : 'error') : 'success',
      text: `Imported ${pluralize(ok, 'memory', 'memories')}${failed ? `, ${pluralize(failed, 'failure')}${firstError ? `: ${firstError}` : ''}` : '.'}`
    })
    if (ok > 0) await refreshMemories()
    if (!failed) {
      setStickyMemories(null)
      setStickyProfile('')
    }
  }

  const scanFiles = async (): Promise<void> => {
    if (fileScanning) return
    setFileScanning(true)
    setFileMessage({ tone: 'info', text: 'Scanning local file names and app shortcuts...' })
    try {
      const status = await window.omi.indexFilesScan()
      setFileIndex(status)
      setFileMessage({
        tone: 'success',
        text: `Indexed ${pluralize(status.filesIndexed, 'item')} in ${status.lastDurationMs ? `${Math.round(status.lastDurationMs / 1000)}s` : 'this scan'}.`
      })
      void buildLocalGraph().catch(() => undefined)
    } catch (scanError) {
      setFileMessage({ tone: 'error', text: `File indexing failed: ${errorMessage(scanError)}` })
    } finally {
      setFileScanning(false)
    }
  }

  const selectImportSource = (nextSource: MemorySource): void => {
    if (extracting || importing) return
    setSource(nextSource)
    setParsed(null)
    setProfile('')
    setImportMessage(null)
  }

  const copyImportPrompt = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(selectedImportApp.prompt)
      setImportMessage({
        tone: 'success',
        text: `Copied ${selectedImportApp.label} prompt. Paste the response below when it replies.`
      })
    } catch (copyError) {
      setImportMessage({
        tone: 'error',
        text: `Could not copy prompt: ${errorMessage(copyError)}`
      })
    }
  }

  const openImportApp = (): void => {
    window.open(selectedImportApp.url, '_blank', 'noopener,noreferrer')
    setImportMessage({
      tone: 'info',
      text: `Opened ${selectedImportApp.label}. Paste the copied prompt there, then paste the response below.`
    })
  }

  const extractDump = async (): Promise<void> => {
    if (extracting) return
    setExtracting(true)
    setParsed(null)
    setProfile('')
    setImportMessage({
      tone: 'info',
      text: `Extracting durable memories from ${source === 'chatgpt' ? 'ChatGPT' : 'Claude'}...`
    })
    const existing = memories.map((m) => m.content)
    try {
      const { memories: list, profile: summary } = await extractMemories(dump, source, existing)
      setParsed(list)
      setProfile(summary)
      setImportMessage({
        tone: list.length > 0 ? 'success' : 'warn',
        text:
          list.length > 0
            ? `Extracted ${pluralize(list.length, 'new memory', 'new memories')}.`
            : 'No new memories found; they may already be saved.'
      })
    } catch (extractError) {
      try {
        const have = new Set(existing.map(normalize))
        const list = (await window.omi.memoryImportParse(dump)).filter(
          (m) => !have.has(normalize(m))
        )
        setParsed(list)
        setImportMessage({
          tone: 'warn',
          text: `AI extraction was unavailable, so Omi used a basic line split: ${errorMessage(extractError)}`
        })
      } catch (fallbackError) {
        setImportMessage({
          tone: 'error',
          text: `Could not extract memories: ${errorMessage(fallbackError)}`
        })
      }
    } finally {
      setExtracting(false)
    }
  }

  const importMemories = async (): Promise<void> => {
    if (!parsed || parsed.length === 0 || importing) return
    const importSource = source
    setImporting(true)
    setImportMessage({
      tone: 'info',
      text: `Importing ${pluralize(parsed.length, 'memory', 'memories')}...`
    })
    let ok = 0
    let failed = 0
    let firstError = ''
    for (const content of parsed) {
      try {
        await omiApi.post('/v3/memories', { content })
        ok++
      } catch (importError) {
        if (!firstError) firstError = errorMessage(importError)
        failed++
      }
    }
    setImporting(false)
    setImportMessage({
      tone: failed ? (ok ? 'warn' : 'error') : 'success',
      text: `Imported ${pluralize(ok, 'memory', 'memories')}${failed ? `, ${pluralize(failed, 'failure')}${firstError ? `: ${firstError}` : ''}` : '.'}`
    })
    if (ok > 0) {
      setImportStats(recordMemoryImport(importSource, ok))
      await refreshMemories()
    }
    if (!failed) {
      setDump('')
      setParsed(null)
      setProfile('')
    }
  }

  const runExport = async (target: ExportTarget): Promise<void> => {
    if (exporting) return
    if (target === 'notion' && (!notionToken.trim() || !notionPage.trim())) {
      setExportMessage({
        tone: 'warn',
        text: 'Enter a Notion integration token and parent page ID first.'
      })
      return
    }
    setExporting(target)
    setExportMessage({
      tone: 'info',
      text: `Preparing ${target === 'file' ? 'plain Markdown' : target === 'obsidian' ? 'Obsidian' : 'Notion'} export...`
    })
    try {
      const all = await fetchAllMemories()
      if (all.length === 0) {
        setExportMessage({ tone: 'warn', text: 'No memories to export yet.' })
        return
      }
      const mems = toExportMemories(all)
      let result: MemoryExportResult
      if (target === 'obsidian') result = await window.omi.memoryExportObsidian(mems)
      else if (target === 'file') result = await window.omi.memoryExportFile(mems)
      else {
        result = await window.omi.memoryExportNotion({
          token: notionToken.trim(),
          parentPageId: notionPage.trim(),
          memories: mems
        })
      }
      setExportMessage(
        result.canceled
          ? { tone: 'warn', text: 'Export canceled.' }
          : {
              tone: 'success',
              text: `Exported ${pluralize(result.count, 'memory', 'memories')}${result.location ? ` to ${result.location}` : '.'}`
            }
      )
    } catch (exportError) {
      setExportMessage({ tone: 'error', text: `Export failed: ${errorMessage(exportError)}` })
    } finally {
      setExporting(null)
    }
  }

  const LIMIT_PER_CATEGORY = 7

  // Unique categories present in the catalog, sorted by their display name.
  const allCategories = useMemo(() => {
    const set = new Set<string>()
    for (const a of apps) set.add(a.category || 'Other')
    return Array.from(set).sort((x, y) => formatCategory(x).localeCompare(formatCategory(y)))
  }, [apps])

  const toggleCat = (cat: string): void => {
    setSelectedCats((s) => {
      const next = new Set(s)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  const categorized = useMemo(() => {
    const installed = apps.filter((a) => enabled.has(a.id))
    let base = tab === 'installed' ? installed : apps
    if (selectedCats.size > 0) {
      base = base.filter((a) => selectedCats.has(a.category || 'Other'))
    }

    if (debouncedQuery.trim()) {
      const q = debouncedQuery.trim().toLowerCase()
      return {
        search: base.filter(
          (a) =>
            a.name?.toLowerCase().includes(q) ||
            a.description?.toLowerCase().includes(q) ||
            a.category?.toLowerCase().includes(q) ||
            a.author?.toLowerCase().includes(q)
        )
      }
    }

    const categories: Record<string, AppEntry[]> = {}
    const sortedByPopularity = [...base].sort((a, b) => {
      const aScore = (a.rating_avg ?? 0) * Math.log((a.installs ?? 1) + 1)
      const bScore = (b.rating_avg ?? 0) * Math.log((b.installs ?? 1) + 1)
      return bScore - aScore
    })

    for (const app of sortedByPopularity) {
      const cat = app.category || 'Other'
      if (!categories[cat]) categories[cat] = []
      if (categories[cat].length < LIMIT_PER_CATEGORY) {
        categories[cat].push(app)
      }
    }

    return categories
  }, [apps, enabled, debouncedQuery, tab, selectedCats])

  const googleCardStatus: StatusKind =
    googleBusy || googleSyncing
      ? 'working'
      : googleLoading
        ? 'loading'
        : !GOOGLE_CONFIGURED
          ? 'not-configured'
          : googleStatus.connected
            ? 'connected'
            : 'optional'
  const stickyCardStatus: StatusKind =
    stickyReading || stickyImporting
      ? 'working'
      : stickyLoading
        ? 'loading'
        : stickyProbe?.error
          ? 'error'
          : stickyProbe?.available
            ? 'optional'
            : 'not-configured'
  const fileCardStatus: StatusKind = fileIndexLoading
    ? 'loading'
    : fileScanning || fileIndex?.running
      ? 'working'
      : (fileIndex?.filesIndexed ?? 0) > 0
        ? 'connected'
        : 'optional'
  const importCardStatus: StatusKind =
    extracting || importing ? 'working' : selectedImportStats ? 'connected' : 'optional'
  const exportCardStatus: StatusKind = memoriesLoading
    ? 'loading'
    : exporting
      ? 'working'
      : memories.length > 0
        ? 'optional'
        : 'not-configured'
  const mcpCardStatus: StatusKind =
    mcpHasKey === null ? 'loading' : mcpHasKey ? 'connected' : 'optional'

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Apps"
        subtitle={
          loading
            ? 'Loading connectors and marketplace...'
            : `${apps.length.toLocaleString()} marketplace apps · ${enabled.size.toLocaleString()} installed`
        }
        actions={
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
              <button
                onClick={() => setTab('all')}
                className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  tab === 'all'
                    ? 'bg-white/15 text-white'
                    : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                Marketplace
              </button>
              <button
                onClick={() => setTab('installed')}
                className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  tab === 'installed'
                    ? 'bg-white/15 text-white'
                    : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                Installed
              </button>
            </div>
            <button
              onClick={onRefresh}
              disabled={refreshing || loading}
              className="btn-ghost px-3 py-2 disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-5xl space-y-8">
          <section className="space-y-4">
            <SectionTitle
              title="Connectors"
              subtitle="Connect cloud services, local Windows data, and AI tools from one place."
            />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <IntegrationCard
                icon={Mail}
                title="Google"
                description="Sync Gmail metadata into memories and Calendar events into tasks."
                status={googleCardStatus}
                statusText={
                  !GOOGLE_CONFIGURED
                    ? 'Google OAuth is not configured for this build.'
                    : googleStatus.connected
                      ? `Connected${googleStatus.email ? ` as ${googleStatus.email}` : ''} · last sync ${formatDateTime(googleStatus.lastSyncAt)}`
                      : 'Optional connector for Gmail and Calendar.'
                }
              >
                <InlineStatus message={googleMessage} />
                {googleStatus.connected ? (
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={syncGoogle}
                      disabled={googleSyncing || googleBusy}
                      className="btn-primary px-3 py-2 text-xs"
                    >
                      {googleSyncing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      {googleSyncing ? 'Syncing...' : 'Sync now'}
                    </button>
                    <button
                      onClick={disconnectGoogle}
                      disabled={googleBusy || googleSyncing}
                      className="btn-ghost px-3 py-2 text-xs"
                    >
                      Disconnect
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={connectGoogle}
                    disabled={googleBusy || !GOOGLE_CONFIGURED}
                    className="btn-ghost px-3 py-2 text-xs"
                  >
                    {googleBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {googleBusy ? 'Connecting...' : 'Connect Google'}
                  </button>
                )}
              </IntegrationCard>

              <IntegrationCard
                icon={StickyNote}
                title="Sticky Notes"
                description="Read local Windows Sticky Notes and turn durable facts into memories."
                status={stickyCardStatus}
                statusText={
                  stickyLoading
                    ? 'Checking this PC for Sticky Notes.'
                    : stickyProbe?.error
                      ? stickyProbe.error
                      : stickyProbe?.available
                        ? `${pluralize(stickyProbe.count, 'note')} found locally.`
                        : 'Sticky Notes was not found on this PC.'
                }
              >
                <InlineStatus message={stickyMessage} />
                <MemoryPreview profile={stickyProfile} memories={stickyMemories} />
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={readSticky}
                    disabled={stickyReading || stickyImporting}
                    className="btn-ghost px-3 py-2 text-xs"
                  >
                    {stickyReading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {stickyReading ? 'Reading...' : 'Analyze notes'}
                  </button>
                  {stickyMemories && stickyMemories.length > 0 && (
                    <button
                      onClick={importSticky}
                      disabled={stickyImporting}
                      className="btn-primary px-3 py-2 text-xs"
                    >
                      {stickyImporting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      {stickyImporting ? 'Importing...' : `Import ${stickyMemories.length}`}
                    </button>
                  )}
                </div>
              </IntegrationCard>

              <IntegrationCard
                icon={FolderSearch}
                title="Local files"
                description="Index file names, folders, and Windows app shortcuts locally for chat context."
                status={fileCardStatus}
                statusText={
                  fileIndex
                    ? `${pluralize(fileIndex.filesIndexed, 'item')} indexed · last scan ${formatDateTime(fileIndex.lastRunAt)}`
                    : 'Local file indexing has not reported status yet.'
                }
              >
                <InlineStatus message={fileMessage} />
                {fileIndex && (
                  <div className="grid grid-cols-2 gap-2 text-xs text-white/50">
                    <div className="glass-subtle px-3 py-2">
                      <span className="block text-white/35">Documents</span>
                      {(fileIndex.byType.document ?? 0).toLocaleString()}
                    </div>
                    <div className="glass-subtle px-3 py-2">
                      <span className="block text-white/35">Apps</span>
                      {(fileIndex.byType.application ?? 0).toLocaleString()}
                    </div>
                  </div>
                )}
                <button
                  onClick={scanFiles}
                  disabled={fileScanning}
                  className="btn-ghost px-3 py-2 text-xs"
                >
                  {fileScanning && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {fileScanning ? 'Indexing...' : 'Re-scan local files'}
                </button>
              </IntegrationCard>
            </div>
          </section>

          <section className="space-y-4">
            <SectionTitle
              title="Import and export"
              subtitle="Move memories in from ChatGPT, Claude, and Sticky Notes, or export them to your own tools."
            />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <IntegrationCard
                icon={Download}
                title="Memory import"
                description="Paste a ChatGPT or Claude memory reply and extract durable facts into Omi."
                status={importCardStatus}
                statusText={
                  parsed && parsed.length > 0
                    ? `${pluralize(parsed.length, 'memory', 'memories')} ready to import.`
                    : selectedImportStats
                      ? `${selectedImportApp.label}: imported ${pluralize(selectedImportStats.count, 'memory', 'memories')} on ${formatDateTime(selectedImportStats.importedAt)}.`
                      : `Copy a prompt for ${selectedImportApp.label}, then paste the response here.`
                }
              >
                <InlineStatus message={importMessage} />
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-white/45">Source</span>
                    {(['chatgpt', 'claude'] as const).map((nextSource) => (
                      <button
                        key={nextSource}
                        onClick={() => selectImportSource(nextSource)}
                        disabled={extracting || importing}
                        className={`rounded-xl px-3 py-1.5 text-xs disabled:opacity-50 ${
                          source === nextSource ? 'btn-primary' : 'btn-ghost'
                        }`}
                      >
                        {nextSource === 'chatgpt' ? 'ChatGPT' : 'Claude'}
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={copyImportPrompt}
                      disabled={extracting || importing}
                      className="btn-ghost inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
                    >
                      <Copy className="h-3.5 w-3.5" />
                      Copy prompt
                    </button>
                    <button
                      onClick={openImportApp}
                      disabled={extracting || importing}
                      className="btn-ghost inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      Open {selectedImportApp.label}
                    </button>
                  </div>
                </div>
                {selectedImportStats && (
                  <div className="grid grid-cols-2 gap-2 text-xs text-white/50">
                    <div className="glass-subtle px-3 py-2">
                      <span className="block text-white/35">Imported</span>
                      {pluralize(selectedImportStats.count, 'memory', 'memories')}
                    </div>
                    <div className="glass-subtle px-3 py-2">
                      <span className="block text-white/35">Last import</span>
                      {formatDateTime(selectedImportStats.importedAt)}
                    </div>
                  </div>
                )}
                <textarea
                  value={dump}
                  onChange={(e) => {
                    setDump(e.target.value)
                    setParsed(null)
                    setProfile('')
                    setImportMessage(null)
                  }}
                  rows={5}
                  placeholder={selectedImportApp.responsePlaceholder}
                  className="input-field resize-none"
                />
                <MemoryPreview profile={profile} memories={parsed} />
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={extractDump}
                    disabled={!dump.trim() || extracting || importing}
                    className="btn-ghost px-3 py-2 text-xs"
                  >
                    {extracting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {extracting ? 'Extracting...' : 'Extract memories'}
                  </button>
                  {parsed && parsed.length > 0 && (
                    <button
                      onClick={importMemories}
                      disabled={importing}
                      className="btn-primary px-3 py-2 text-xs"
                    >
                      {importing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      {importing ? 'Importing...' : `Import ${parsed.length}`}
                    </button>
                  )}
                </div>
              </IntegrationCard>

              <IntegrationCard
                icon={Upload}
                title="Memory export"
                description="Export Omi memories as Markdown for Obsidian, a plain file, or Notion."
                status={exportCardStatus}
                statusText={
                  memoriesError
                    ? `Could not load memory count: ${memoriesError}`
                    : memoriesLoading
                      ? 'Loading memory count...'
                      : `${pluralize(memories.length, 'memory', 'memories')} loaded for status; export fetches the full set.`
                }
              >
                <InlineStatus message={exportMessage} />
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <button
                    onClick={() => runExport('obsidian')}
                    disabled={Boolean(exporting)}
                    className="btn-ghost px-3 py-2 text-xs"
                  >
                    {exporting === 'obsidian' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    <Database className="h-3.5 w-3.5" />
                    Obsidian vault
                  </button>
                  <button
                    onClick={() => runExport('file')}
                    disabled={Boolean(exporting)}
                    className="btn-ghost px-3 py-2 text-xs"
                  >
                    {exporting === 'file' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    <FileText className="h-3.5 w-3.5" />
                    Plain file
                  </button>
                </div>
                <div className="space-y-2 border-t border-white/5 pt-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-white/65">Notion</span>
                    <StatusBadge
                      kind={notionToken.trim() && notionPage.trim() ? 'optional' : 'not-configured'}
                    />
                  </div>
                  <input
                    value={notionToken}
                    onChange={(e) => setNotionToken(e.target.value)}
                    placeholder="Notion integration token"
                    className="input-field py-2 text-xs"
                  />
                  <input
                    value={notionPage}
                    onChange={(e) => setNotionPage(e.target.value)}
                    placeholder="Parent page ID"
                    className="input-field py-2 text-xs"
                  />
                  <button
                    onClick={() => runExport('notion')}
                    disabled={Boolean(exporting)}
                    className="btn-ghost px-3 py-2 text-xs"
                  >
                    {exporting === 'notion' && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    <Cloud className="h-3.5 w-3.5" />
                    Export to Notion
                  </button>
                </div>
              </IntegrationCard>
            </div>
          </section>

          <section className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <SectionTitle
                title="Hosted MCP connectors"
                subtitle="Give ChatGPT, Claude, Claude Code, Codex, or another MCP client live access to Omi memories."
              />
              <StatusBadge kind={mcpCardStatus} />
            </div>
            <McpConnectorSetup onKeyStateChange={setMcpHasKey} />
          </section>

          <section className="space-y-5 pb-4">
            <SectionTitle
              title="Marketplace apps"
              subtitle="Install optional Omi apps after your core connectors are set up."
            />
            {loading && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="surface-card p-5">
                    <div className="mb-3 flex items-start gap-3">
                      <div className="skeleton h-12 w-12 shrink-0 rounded-2xl" />
                      <div className="flex-1 space-y-2">
                        <div className="skeleton h-4 w-3/4" />
                        <div className="skeleton h-3 w-1/3" />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <div className="skeleton h-3 w-full" />
                      <div className="skeleton h-3 w-5/6" />
                      <div className="skeleton h-3 w-2/3" />
                    </div>
                  </div>
                ))}
              </div>
            )}
            {error && (
              <div className="glass-subtle mb-5 flex items-start gap-2 px-4 py-3 text-sm text-white/60">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-white/45" />
                {error}
              </div>
            )}
            {!loading && !error && (
              <div className="space-y-5">
                <div className="flex items-center gap-2">
                  <div className="glass-subtle flex flex-1 items-center gap-2 px-4 py-2.5">
                    <Search className="h-4 w-4 text-white/45" />
                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Search apps..."
                      className="flex-1 border-0 bg-transparent text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-0"
                    />
                    {query && (
                      <button
                        onClick={() => setQuery('')}
                        className="text-xs text-white/45 hover:text-white"
                      >
                        Clear
                      </button>
                    )}
                  </div>

                  <div ref={filterRef} className="relative">
                    <button
                      onClick={() => setFilterOpen((o) => !o)}
                      className={`glass-subtle flex items-center gap-2 px-4 py-2.5 text-sm transition-colors duration-200 ${
                        filterOpen || selectedCats.size > 0
                          ? 'text-white'
                          : 'text-white/55 hover:text-white/80'
                      }`}
                      title="Filter by category"
                    >
                      <SlidersHorizontal className="h-4 w-4" />
                      <span className="hidden sm:inline">Filter</span>
                      {selectedCats.size > 0 && (
                        <span className="flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-white/20 px-1.5 text-[11px] font-semibold text-white">
                          {selectedCats.size}
                        </span>
                      )}
                    </button>

                    {filterOpen && (
                      <div className="surface-card absolute right-0 z-30 mt-2 max-h-80 w-60 overflow-y-auto p-2 shadow-xl">
                        <div className="flex items-center justify-between px-2 py-1.5">
                          <span className="text-xs font-semibold uppercase tracking-wide text-white/45">
                            Categories
                          </span>
                          {selectedCats.size > 0 && (
                            <button
                              onClick={() => setSelectedCats(new Set())}
                              className="text-[11px] text-white/45 hover:text-white"
                            >
                              Clear
                            </button>
                          )}
                        </div>
                        {allCategories.length === 0 ? (
                          <div className="px-2 py-2 text-xs text-white/45">No categories</div>
                        ) : (
                          allCategories.map((cat) => {
                            const checked = selectedCats.has(cat)
                            return (
                              <button
                                key={cat}
                                onClick={() => toggleCat(cat)}
                                className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 text-left text-sm text-white/75 transition-colors duration-150 hover:bg-white/5"
                              >
                                <span
                                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-md border transition-colors duration-150 ${
                                    checked
                                      ? 'border-white/30 bg-white/20 text-white'
                                      : 'border-white/20 bg-transparent'
                                  }`}
                                >
                                  {checked && <Check className="h-3 w-3" />}
                                </span>
                                <span className="truncate">{formatCategory(cat)}</span>
                              </button>
                            )
                          })
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {selectedCats.size > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    {Array.from(selectedCats).map((cat) => (
                      <button
                        key={cat}
                        onClick={() => toggleCat(cat)}
                        className="badge flex items-center gap-1 hover:text-white"
                      >
                        {formatCategory(cat)}
                        <X className="h-3 w-3" />
                      </button>
                    ))}
                  </div>
                )}

                {query.trim() && categorized.search && categorized.search.length === 0 && (
                  <EmptyState
                    icon={LayoutGrid}
                    title="No apps match"
                    description="Try a different search."
                  />
                )}

                {!query.trim() && Object.keys(categorized).length === 0 && (
                  <EmptyState
                    icon={LayoutGrid}
                    title={tab === 'installed' ? 'No apps installed' : 'No apps available'}
                    description={
                      tab === 'installed'
                        ? 'Browse the Marketplace tab to find apps to install.'
                        : 'Try again later.'
                    }
                  />
                )}

                {query.trim() ? (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {categorized.search?.map((a) => (
                      <AppCard
                        key={a.id}
                        app={a}
                        isOn={enabled.has(a.id)}
                        isBusy={busy.has(a.id)}
                        onToggle={toggle}
                      />
                    ))}
                  </div>
                ) : (
                  Object.entries(categorized)
                    .sort(([catA], [catB]) => {
                      const order = [
                        'Most Popular',
                        'Featured',
                        'Integrations',
                        'Chat Assistants',
                        'Summary Apps',
                        'Notifications'
                      ]
                      const aIdx = order.indexOf(formatCategory(catA))
                      const bIdx = order.indexOf(formatCategory(catB))
                      return (aIdx === -1 ? Infinity : aIdx) - (bIdx === -1 ? Infinity : bIdx)
                    })
                    .map(([category, categoryApps]) => (
                      <div key={category} className="space-y-3">
                        <h2 className="text-sm font-semibold text-white/80">
                          {formatCategory(category)}
                        </h2>
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                          {categoryApps.map((a) => (
                            <AppCard
                              key={a.id}
                              app={a}
                              isOn={enabled.has(a.id)}
                              isBusy={busy.has(a.id)}
                              onToggle={toggle}
                            />
                          ))}
                        </div>
                      </div>
                    ))
                )}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
