import { useEffect, useMemo, useState } from 'react'
import {
  Check,
  Cloud,
  Database,
  Download,
  FileText,
  FolderSearch,
  Loader2,
  Mail,
  RefreshCw,
  Search,
  Sparkles,
  StickyNote,
  Upload,
  Wrench
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
import { getPreferences, setPreferences } from '../lib/preferences'
import { useMemories, type Memory } from '../hooks/useMemories'
import type {
  ExportMemory,
  FileIndexStatus,
  GoogleStatus,
  MemoryExportResult,
  SkillEntry,
  SkillsListResult
} from '../../../shared/types'

type Tab = 'connectors' | 'skills'
type StatusKind = 'connected' | 'optional' | 'not-configured' | 'working' | 'loading' | 'error'
type ExportTarget = 'obsidian' | 'file'
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

function errorMessage(error: unknown): string {
  return (
    (error as { response?: { data?: { detail?: string }; status?: number }; message?: string })
      .response?.data?.detail ??
    (error as { response?: { status?: number } }).response?.status?.toString() ??
    (error as Error).message
  )
}

function toExportMemories(memories: Memory[]): ExportMemory[] {
  return memories.map((memory) => ({
    content: memory.content,
    category: memory.category ?? null,
    createdAt: memory.created_at
  }))
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

function ConnectorCard({
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
    <section className="surface-card flex min-h-[18rem] flex-col p-5">
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

function SkillCard({
  skill,
  active,
  onToggle
}: {
  skill: SkillEntry
  active: boolean
  onToggle: () => void
}): React.JSX.Element {
  return (
    <article
      className={`surface-card-interactive flex h-full flex-col p-5 ${
        active ? 'border-[color:var(--accent)]/60 bg-[color:var(--accent)]/10' : ''
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-base font-semibold text-white">{skill.name}</h2>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-white/55">
            {skill.description || 'No description in SKILL.md'}
          </p>
        </div>
        <button
          onClick={onToggle}
          className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-colors ${
            active
              ? 'border-[color:var(--accent)]/70 bg-[color:var(--accent)]/25 text-white'
              : 'border-white/15 text-white/55 hover:bg-white/5 hover:text-white'
          }`}
          aria-label={active ? `Disable ${skill.name}` : `Enable ${skill.name}`}
          title={active ? 'Active in Pi chat' : 'Add to Pi chat'}
        >
          {active ? <Check className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
        </button>
      </div>
      <div className="mt-auto truncate text-[11px] text-white/35">{skill.relativePath}</div>
    </article>
  )
}

export function Apps(): React.JSX.Element {
  const { memories, loading: memoriesLoading, refresh: refreshMemories } = useMemories()
  const [tab, setTab] = useState<Tab>('connectors')
  const [refreshing, setRefreshing] = useState(false)

  const [skills, setSkills] = useState<SkillEntry[]>([])
  const [skillRoots, setSkillRoots] = useState<string[]>([])
  const [skillsLoading, setSkillsLoading] = useState(true)
  const [skillsError, setSkillsError] = useState<string | null>(null)
  const [skillQuery, setSkillQuery] = useState('')
  const [enabledSkillIds, setEnabledSkillIds] = useState<Set<string>>(
    () => new Set(getPreferences().enabledSkillIds ?? [])
  )

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

  const [exporting, setExporting] = useState<ExportTarget | null>(null)
  const [exportMessage, setExportMessage] = useState<StatusMessage>(null)

  const loadSkills = async (): Promise<void> => {
    setSkillsError(null)
    try {
      const result: SkillsListResult = await window.omi.skillsList()
      setSkills(result.skills)
      setSkillRoots(result.roots)
    } catch (error) {
      setSkillsError(errorMessage(error))
    } finally {
      setSkillsLoading(false)
    }
  }

  useEffect(() => {
    void loadSkills()
  }, [])

  useEffect(() => {
    let cancelled = false
    window.omi
      .readStickyNotes()
      .then((result) => {
        if (!cancelled) {
          setStickyProbe({
            available: result.available,
            count: result.notes.length,
            error: result.error
          })
        }
      })
      .catch((error) => {
        if (!cancelled) setStickyProbe({ available: false, count: 0, error: errorMessage(error) })
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
      .catch((error) => {
        if (!cancelled)
          setGoogleMessage({
            tone: 'error',
            text: `Could not check Google: ${errorMessage(error)}`
          })
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
      .catch((error) => {
        if (!cancelled)
          setFileMessage({
            tone: 'error',
            text: `Could not check local files: ${errorMessage(error)}`
          })
      })
      .finally(() => {
        if (!cancelled) setFileIndexLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const refreshAll = async (): Promise<void> => {
    if (refreshing) return
    setRefreshing(true)
    await Promise.all([
      loadSkills(),
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

  const toggleSkill = (id: string): void => {
    setEnabledSkillIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      setPreferences({ enabledSkillIds: Array.from(next) })
      return next
    })
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
    } catch (error) {
      setGoogleMessage({ tone: 'error', text: `Could not connect Google: ${errorMessage(error)}` })
    } finally {
      setGoogleBusy(false)
    }
  }

  const disconnectGoogle = async (): Promise<void> => {
    if (googleBusy || !GOOGLE_CONFIGURED) return
    setGoogleBusy(true)
    try {
      const status = await window.omi.googleDisconnect()
      setGoogleStatus(status)
      setGoogleMessage({ tone: 'success', text: 'Google disconnected.' })
    } catch (error) {
      setGoogleMessage({
        tone: 'error',
        text: `Could not disconnect Google: ${errorMessage(error)}`
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
      const out = await runGoogleSync(memories.map((memory) => memory.content))
      if (out.memoriesAdded > 0) await refreshMemories()
      setGoogleStatus(await window.omi.googleStatus())
      setGoogleMessage({
        tone: out.errors.length > 0 ? 'warn' : 'success',
        text:
          out.errors.length > 0
            ? `Sync finished with errors: ${out.errors.join('; ')}`
            : `Synced ${pluralize(out.memoriesAdded, 'memory', 'memories')} and ${pluralize(out.tasksAdded, 'task')}.`
      })
    } catch (error) {
      setGoogleMessage({ tone: 'error', text: `Google sync failed: ${errorMessage(error)}` })
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
      if (!result.available || result.notes.length === 0) {
        setStickyMessage({ tone: 'warn', text: 'No readable Sticky Notes were found on this PC.' })
        return
      }
      const notesText = result.notes.map((note) => note.text).join('\n\n---\n\n')
      const extracted = await extractNoteMemories(
        notesText,
        memories.map((memory) => memory.content)
      )
      setStickyMemories(extracted.memories)
      setStickyProfile(extracted.profile)
      setStickyMessage({
        tone: extracted.memories.length > 0 ? 'success' : 'warn',
        text:
          extracted.memories.length > 0
            ? `Found ${pluralize(extracted.memories.length, 'new memory', 'new memories')} from ${pluralize(result.notes.length, 'note')}.`
            : 'No new durable memories were found in Sticky Notes.'
      })
    } catch (error) {
      setStickyMessage({
        tone: 'error',
        text: `Could not read Sticky Notes: ${errorMessage(error)}`
      })
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
        ok += 1
      } catch (error) {
        if (!firstError) firstError = errorMessage(error)
        failed += 1
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
    } catch (error) {
      setFileMessage({ tone: 'error', text: `File indexing failed: ${errorMessage(error)}` })
    } finally {
      setFileScanning(false)
    }
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
    const existing = memories.map((memory) => memory.content)
    try {
      const extracted = await extractMemories(dump, source, existing)
      setParsed(extracted.memories)
      setProfile(extracted.profile)
      setImportMessage({
        tone: extracted.memories.length > 0 ? 'success' : 'warn',
        text:
          extracted.memories.length > 0
            ? `Extracted ${pluralize(extracted.memories.length, 'new memory', 'new memories')}.`
            : 'No new memories found; they may already be saved.'
      })
    } catch (error) {
      try {
        const have = new Set(existing.map(normalize))
        const list = (await window.omi.memoryImportParse(dump)).filter(
          (memory) => !have.has(normalize(memory))
        )
        setParsed(list)
        setImportMessage({
          tone: 'warn',
          text: `AI extraction was unavailable, so Omi used a basic line split: ${errorMessage(error)}`
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
    setImporting(true)
    let ok = 0
    let failed = 0
    let firstError = ''
    for (const content of parsed) {
      try {
        await omiApi.post('/v3/memories', { content })
        ok += 1
      } catch (error) {
        if (!firstError) firstError = errorMessage(error)
        failed += 1
      }
    }
    setImporting(false)
    setImportMessage({
      tone: failed ? (ok ? 'warn' : 'error') : 'success',
      text: `Imported ${pluralize(ok, 'memory', 'memories')}${failed ? `, ${pluralize(failed, 'failure')}${firstError ? `: ${firstError}` : ''}` : '.'}`
    })
    if (ok > 0) await refreshMemories()
    if (!failed) {
      setDump('')
      setParsed(null)
      setProfile('')
    }
  }

  const runExport = async (target: ExportTarget): Promise<void> => {
    if (exporting) return
    setExporting(target)
    setExportMessage({
      tone: 'info',
      text: `Preparing ${target === 'file' ? 'Markdown' : 'Obsidian'} export...`
    })
    try {
      const all = await fetchAllMemories()
      if (all.length === 0) {
        setExportMessage({ tone: 'warn', text: 'No memories to export yet.' })
        return
      }
      const mems = toExportMemories(all)
      const result: MemoryExportResult =
        target === 'obsidian'
          ? await window.omi.memoryExportObsidian(mems)
          : await window.omi.memoryExportFile(mems)
      setExportMessage(
        result.canceled
          ? { tone: 'warn', text: 'Export canceled.' }
          : {
              tone: 'success',
              text: `Exported ${pluralize(result.count, 'memory', 'memories')}${result.location ? ` to ${result.location}` : '.'}`
            }
      )
    } catch (error) {
      setExportMessage({ tone: 'error', text: `Export failed: ${errorMessage(error)}` })
    } finally {
      setExporting(null)
    }
  }

  const filteredSkills = useMemo(() => {
    const query = skillQuery.trim().toLowerCase()
    if (!query) return skills
    return skills.filter((skill) =>
      [skill.name, skill.description, skill.relativePath].some((value) =>
        value.toLowerCase().includes(query)
      )
    )
  }, [skills, skillQuery])

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
    extracting || importing ? 'working' : parsed ? 'connected' : 'optional'
  const exportCardStatus: StatusKind = memoriesLoading
    ? 'loading'
    : exporting
      ? 'working'
      : memories.length > 0
        ? 'optional'
        : 'not-configured'

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Integrations"
        subtitle={
          tab === 'skills'
            ? `${enabledSkillIds.size.toLocaleString()} active skills · ${skills.length.toLocaleString()} found`
            : 'Connectors, local sources, imports, and exports'
        }
        actions={
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-black/20 p-1">
              <button
                onClick={() => setTab('connectors')}
                className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  tab === 'connectors'
                    ? 'bg-white/15 text-white'
                    : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                Connectors
              </button>
              <button
                onClick={() => setTab('skills')}
                className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-200 ${
                  tab === 'skills'
                    ? 'bg-white/15 text-white'
                    : 'text-white/55 hover:bg-white/5 hover:text-white/80'
                }`}
              >
                Skills
              </button>
            </div>
            <button
              onClick={() => void refreshAll()}
              disabled={refreshing}
              className="btn-ghost inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        }
      />

      {tab === 'connectors' ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-8 lg:px-10">
          <div className="mb-8">
            <McpConnectorSetup />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <ConnectorCard
              icon={Mail}
              title="Google"
              description="Gmail and Calendar sync for memories and action items."
              status={googleCardStatus}
              statusText={
                !GOOGLE_CONFIGURED
                  ? 'Google OAuth is not configured in this build.'
                  : googleStatus.connected
                    ? `Signed in${googleStatus.email ? ` as ${googleStatus.email}` : ''}.`
                    : 'Ready to connect a Google account.'
              }
            >
              <div className="flex flex-wrap gap-2">
                {googleStatus.connected ? (
                  <>
                    <button
                      className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
                      disabled={googleSyncing}
                      onClick={() => void syncGoogle()}
                    >
                      {googleSyncing ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <RefreshCw className="h-3.5 w-3.5" />
                      )}
                      Sync now
                    </button>
                    <button
                      className="btn-ghost px-3 py-2 text-xs disabled:opacity-50"
                      disabled={googleBusy}
                      onClick={() => void disconnectGoogle()}
                    >
                      Disconnect
                    </button>
                  </>
                ) : (
                  <button
                    className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
                    disabled={!GOOGLE_CONFIGURED || googleBusy}
                    onClick={() => void connectGoogle()}
                  >
                    {googleBusy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Cloud className="h-3.5 w-3.5" />
                    )}
                    Connect
                  </button>
                )}
              </div>
              <InlineStatus message={googleMessage} />
            </ConnectorCard>

            <ConnectorCard
              icon={StickyNote}
              title="Sticky Notes"
              description="Read local Windows Sticky Notes and import durable memories."
              status={stickyCardStatus}
              statusText={
                stickyLoading
                  ? 'Checking this PC...'
                  : stickyProbe?.available
                    ? `${pluralize(stickyProbe.count, 'note')} detected.`
                    : stickyProbe?.error || 'No Sticky Notes database found.'
              }
            >
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
                  disabled={stickyReading || stickyImporting}
                  onClick={() => void readSticky()}
                >
                  {stickyReading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <FileText className="h-3.5 w-3.5" />
                  )}
                  Read notes
                </button>
                <button
                  className="btn-ghost px-3 py-2 text-xs disabled:opacity-50"
                  disabled={!stickyMemories?.length || stickyImporting}
                  onClick={() => void importSticky()}
                >
                  Import {stickyMemories?.length ? stickyMemories.length : ''}
                </button>
              </div>
              <InlineStatus message={stickyMessage} />
            </ConnectorCard>

            <ConnectorCard
              icon={FolderSearch}
              title="Local files"
              description="Index app shortcuts and local file names for profile context."
              status={fileCardStatus}
              statusText={
                fileIndexLoading
                  ? 'Checking index...'
                  : `${pluralize(fileIndex?.filesIndexed ?? 0, 'item')} indexed.`
              }
            >
              <button
                className="btn-primary inline-flex items-center gap-2 px-3 py-2 text-xs disabled:opacity-50"
                disabled={fileScanning}
                onClick={() => void scanFiles()}
              >
                {fileScanning ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Database className="h-3.5 w-3.5" />
                )}
                Scan local files
              </button>
              <InlineStatus message={fileMessage} />
            </ConnectorCard>

            <ConnectorCard
              icon={Upload}
              title="Memory import"
              description="Extract profile memories from pasted ChatGPT or Claude exports."
              status={importCardStatus}
              statusText={
                parsed
                  ? `${pluralize(parsed.length, 'memory', 'memories')} ready to import.`
                  : 'Paste an export and extract memories.'
              }
            >
              <div className="flex flex-wrap gap-2">
                <select
                  value={source}
                  onChange={(event) => setSource(event.target.value as MemorySource)}
                  className="rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-xs text-white outline-none"
                >
                  <option value="chatgpt" className="bg-neutral-900">
                    ChatGPT
                  </option>
                  <option value="claude" className="bg-neutral-900">
                    Claude
                  </option>
                </select>
                <button
                  className="btn-primary px-3 py-2 text-xs disabled:opacity-50"
                  disabled={!dump.trim() || extracting}
                  onClick={() => void extractDump()}
                >
                  Extract
                </button>
                <button
                  className="btn-ghost px-3 py-2 text-xs disabled:opacity-50"
                  disabled={!parsed?.length || importing}
                  onClick={() => void importMemories()}
                >
                  Import
                </button>
              </div>
              <textarea
                value={dump}
                onChange={(event) => setDump(event.target.value)}
                placeholder="Paste export text"
                className="input-field min-h-24 resize-none text-xs"
              />
              {profile && (
                <div className="glass-subtle px-4 py-3 text-xs text-white/60">{profile}</div>
              )}
              <InlineStatus message={importMessage} />
            </ConnectorCard>

            <ConnectorCard
              icon={Download}
              title="Memory export"
              description="Write saved memories to local Markdown or Obsidian."
              status={exportCardStatus}
              statusText={`${pluralize(memories.length, 'memory', 'memories')} currently loaded.`}
            >
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn-primary px-3 py-2 text-xs disabled:opacity-50"
                  disabled={!!exporting || memoriesLoading}
                  onClick={() => void runExport('file')}
                >
                  Markdown file
                </button>
                <button
                  className="btn-ghost px-3 py-2 text-xs disabled:opacity-50"
                  disabled={!!exporting || memoriesLoading}
                  onClick={() => void runExport('obsidian')}
                >
                  Obsidian
                </button>
              </div>
              <InlineStatus message={exportMessage} />
            </ConnectorCard>
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-8 lg:px-10">
          <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="glass-subtle flex min-w-0 flex-1 items-center gap-2 px-4 py-2.5">
              <Search className="h-4 w-4 shrink-0 text-white/35" />
              <input
                value={skillQuery}
                onChange={(event) => setSkillQuery(event.target.value)}
                placeholder="Search skills"
                className="min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-white/35"
              />
            </div>
            <div className="text-xs text-white/40">
              {skillRoots.length.toLocaleString()} roots scanned
            </div>
          </div>

          {skillsError && (
            <div className="glass-subtle mb-5 px-4 py-3 text-sm text-red-200/90">{skillsError}</div>
          )}

          {skillsLoading ? (
            <EmptyState icon={Loader2} title="Loading skills" />
          ) : filteredSkills.length === 0 ? (
            <EmptyState
              icon={Wrench}
              title="No skills found"
              description="Install or configure skills, then refresh."
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filteredSkills.map((skill) => (
                <SkillCard
                  key={skill.id}
                  skill={skill}
                  active={enabledSkillIds.has(skill.id)}
                  onToggle={() => toggleSkill(skill.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
