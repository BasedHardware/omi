import { useEffect, useState } from 'react'
import { Download, Upload, Wrench, FolderSearch, Network, RotateCcw } from 'lucide-react'
import { omiApi } from '../../../lib/apiClient'
import { toast } from '../../../lib/toast'
import { extractMemories, type MemorySource } from '../../../lib/memoryExtract'
import { buildLocalGraph } from '../../../lib/kgSynthesis'
import { summarizeMemories, appIndexMemoryIds, type MemoryBreakdown } from '../../../lib/memoryCleanup'
import { useMemories, type Memory } from '../../../hooks/useMemories'
import { resetOnboarding } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { IntegrationsTab } from './IntegrationsTab'
import type {
  ExportMemory,
  FileIndexStatus,
  LocalKGStatus,
  MemoryExportResult
} from '../../../../../shared/types'

export function AdvancedTab(): React.JSX.Element {
  const { memories, refresh } = useMemories()

  // --- File indexing ---
  const [fileIndex, setFileIndex] = useState<FileIndexStatus | null>(null)
  const [scanning, setScanning] = useState(false)
  useEffect(() => {
    window.omi.indexFilesStatus().then(setFileIndex).catch(() => setFileIndex(null))
  }, [])
  const rescan = async (): Promise<void> => {
    if (scanning) return
    setScanning(true)
    try {
      setFileIndex(await window.omi.indexFilesScan())
      toast('File index updated', { tone: 'success' })
      void buildLocalGraph().catch(() => {})
    } catch (e) {
      toast('File indexing failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setScanning(false)
    }
  }

  // --- Knowledge graph ---
  const [kgStatus, setKgStatus] = useState<LocalKGStatus | null>(null)
  const [rebuildingKg, setRebuildingKg] = useState(false)
  useEffect(() => {
    window.omi.kgStatus().then(setKgStatus).catch(() => setKgStatus(null))
  }, [])
  const rebuildKg = async (): Promise<void> => {
    if (rebuildingKg) return
    setRebuildingKg(true)
    try {
      setKgStatus(await buildLocalGraph())
      toast('Knowledge graph rebuilt', { tone: 'success' })
    } catch (e) {
      toast('Knowledge graph rebuild failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setRebuildingKg(false)
    }
  }

  // --- Import memories ---
  const [dump, setDump] = useState('')
  const [source, setSource] = useState<MemorySource>('chatgpt')
  const [parsed, setParsed] = useState<string[] | null>(null)
  const [profile, setProfile] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [importing, setImporting] = useState(false)

  const extractDump = async (): Promise<void> => {
    if (extracting) return
    setExtracting(true)
    setProfile('')
    const existing = memories.map((m) => m.content)
    try {
      const { memories: list, profile: summary } = await extractMemories(dump, source, existing)
      setParsed(list)
      setProfile(summary)
      if (list.length === 0) toast('No new memories found — they may already be saved', { tone: 'warn' })
    } catch (e) {
      console.warn('[memoryImport] AI extraction failed, falling back to split:', e)
      try {
        const norm = (s: string): string =>
          s.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, '').replace(/\s+/g, ' ').trim()
        const have = new Set(existing.map(norm))
        const list = (await window.omi.memoryImportParse(dump)).filter((m) => !have.has(norm(m)))
        setParsed(list)
        toast('AI extraction unavailable — used a basic line split', {
          tone: 'warn',
          body: (e as Error).message
        })
      } catch (e2) {
        toast('Could not extract memories', { tone: 'error', body: (e2 as Error).message })
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
        ok++
      } catch (e) {
        const msg =
          (e as { response?: { status?: number; data?: { detail?: string } }; message: string })
            .response?.data?.detail ??
          (e as { response?: { status?: number } }).response?.status?.toString() ??
          (e as Error).message
        if (!firstError) firstError = msg
        failed++
      }
    }
    setImporting(false)
    toast(`Imported ${ok} memor${ok === 1 ? 'y' : 'ies'}${failed ? `, ${failed} failed` : ''}`, {
      tone: failed ? (ok ? 'warn' : 'error') : 'success',
      body: failed ? firstError : undefined
    })
    if (ok > 0) await refresh()
    if (!failed) {
      setDump('')
      setParsed(null)
      setProfile('')
    }
  }

  // --- Export memories ---
  const [notionToken, setNotionToken] = useState('')
  const [notionPage, setNotionPage] = useState('')
  const [exporting, setExporting] = useState(false)
  const toExportMemories = (): ExportMemory[] =>
    memories.map((m) => ({ content: m.content, category: m.category ?? null, createdAt: m.created_at }))

  const runExport = async (target: 'obsidian' | 'file' | 'notion'): Promise<void> => {
    if (exporting) return
    if (memories.length === 0) {
      toast('No memories to export yet', { tone: 'warn' })
      return
    }
    if (target === 'notion' && (!notionToken.trim() || !notionPage.trim())) {
      toast('Enter your Notion token and parent page ID', { tone: 'warn' })
      return
    }
    setExporting(true)
    try {
      const mems = toExportMemories()
      let r: MemoryExportResult
      if (target === 'obsidian') r = await window.omi.memoryExportObsidian(mems)
      else if (target === 'file') r = await window.omi.memoryExportFile(mems)
      else
        r = await window.omi.memoryExportNotion({
          token: notionToken.trim(),
          parentPageId: notionPage.trim(),
          memories: mems
        })
      if (!r.canceled) {
        toast(`Exported ${r.count} memor${r.count === 1 ? 'y' : 'ies'}`, { tone: 'success', body: r.location })
      }
    } catch (e) {
      toast('Export failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setExporting(false)
    }
  }

  // --- Memory maintenance ---
  const [memBreakdown, setMemBreakdown] = useState<MemoryBreakdown | null>(null)
  const [memAllMemories, setMemAllMemories] = useState<Memory[]>([])
  const [memAuditing, setMemAuditing] = useState(false)
  const [memDeleting, setMemDeleting] = useState(false)
  const [memDeleteProgress, setMemDeleteProgress] = useState(0)

  const fetchAllMemories = async (): Promise<Memory[]> => {
    const byId = new Map<string, Memory>()
    for (let offset = 0; offset < 100000; offset += 200) {
      const r = await omiApi.get('/v3/memories', { params: { limit: 200, offset } })
      const page = (Array.isArray(r.data) ? r.data : (r.data?.memories ?? [])) as Memory[]
      let added = 0
      for (const m of page) {
        if (m.id && !byId.has(m.id)) {
          byId.set(m.id, m)
          added++
        }
      }
      if (page.length < 200 || added === 0) break
    }
    return [...byId.values()]
  }

  const auditMemories = async (): Promise<void> => {
    if (memAuditing || memDeleting) return
    setMemAuditing(true)
    try {
      const all = await fetchAllMemories()
      setMemAllMemories(all)
      setMemBreakdown(summarizeMemories(all))
    } catch (e) {
      toast('Could not load memories', { tone: 'error', body: (e as Error).message })
    } finally {
      setMemAuditing(false)
    }
  }

  const deleteAppIndexMemories = async (): Promise<void> => {
    const ids = appIndexMemoryIds(memAllMemories)
    if (ids.length === 0 || memDeleting) return
    if (!window.confirm(`Permanently delete ${ids.length} app/file-index memories? This cannot be undone.`)) return
    setMemDeleting(true)
    setMemDeleteProgress(0)
    const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))
    let deleted = 0
    let failed = 0
    let firstError = ''
    let paceMs = 1100

    const deleteIdPaced = async (id: string): Promise<'ok' | 'gone' | 'fail'> => {
      for (let attempt = 0; attempt < 30; attempt++) {
        try {
          await omiApi.delete(`/v3/memories/${id}`, { ...({ __noRetry: true } as object) })
          return 'ok'
        } catch (e) {
          const resp = (e as { response?: { status?: number; headers?: Record<string, string> } }).response
          const status = resp?.status
          if (status === 404) return 'gone'
          if (status === 429) {
            paceMs = 1100
            const ra = Number(resp?.headers?.['retry-after'])
            await sleep(Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(3000 * 1.6 ** attempt, 60_000))
            continue
          }
          if (!firstError) firstError = status ? `HTTP ${status}` : (e as Error).message
          return 'fail'
        }
      }
      return 'fail'
    }

    try {
      for (let i = 0; i < ids.length; i++) {
        const r = await deleteIdPaced(ids[i])
        if (r === 'ok' || r === 'gone') deleted++
        else failed++
        if (i % 10 === 0 || i === ids.length - 1) setMemDeleteProgress(deleted)
        if (paceMs) await sleep(paceMs)
      }
      toast(`Deleted ${deleted} of ${ids.length} memories`, {
        tone: failed ? 'warn' : 'success',
        body: failed ? `${failed} failed${firstError ? ` — ${firstError}` : ''}. Analyze again to retry.` : undefined
      })
    } catch (e) {
      toast('Delete failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setMemDeleting(false)
    }
    await refresh()
    await auditMemories()
  }

  const replayOnboarding = (): void => {
    resetOnboarding()
    window.location.reload()
  }

  return (
    <>
      <SettingRow
        icon={Download}
        title="Import memories"
        subtitle="Paste a ChatGPT/Claude “everything you remember about me” reply; Omi extracts distinct, durable facts."
        keywords="import chatgpt claude memories paste extract"
      >
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-sm text-text-tertiary">Exported from</span>
            {(['chatgpt', 'claude'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSource(s)}
                className={`rounded-md px-3 py-1 text-sm ${source === s ? 'btn-primary' : 'btn-ghost'}`}
              >
                {s === 'chatgpt' ? 'ChatGPT' : 'Claude'}
              </button>
            ))}
          </div>
          <textarea
            value={dump}
            onChange={(e) => {
              setDump(e.target.value)
              setParsed(null)
              setProfile('')
            }}
            rows={5}
            placeholder="Paste the assistant’s full reply here…"
            className="input-field resize-none"
          />
          <div className="flex items-center gap-2">
            <button onClick={extractDump} disabled={!dump.trim() || extracting || importing} className="btn-ghost disabled:opacity-40">
              {extracting ? 'Extracting…' : 'Extract memories'}
            </button>
            {parsed && parsed.length > 0 && (
              <button onClick={importMemories} disabled={importing} className="btn-primary px-4 py-2 disabled:opacity-40">
                {importing ? 'Importing…' : `Import ${parsed.length} memor${parsed.length === 1 ? 'y' : 'ies'}`}
              </button>
            )}
          </div>
          {profile && (
            <p className="glass-subtle rounded-lg px-4 py-3 text-sm italic text-text-tertiary">{profile}</p>
          )}
          {parsed && parsed.length > 0 && (
            <ul className="glass-subtle max-h-40 overflow-y-auto rounded-lg px-4 py-3 text-sm text-text-tertiary">
              {parsed.map((m, i) => (
                <li key={i} className="py-0.5">• {m}</li>
              ))}
            </ul>
          )}
        </div>
      </SettingRow>

      <SettingRow
        icon={Upload}
        title="Export memories"
        subtitle={`Export your ${memories.length} memor${memories.length === 1 ? 'y' : 'ies'} as Markdown (Obsidian, a plain file, or Notion).`}
        keywords="export obsidian notion file markdown"
      >
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <button onClick={() => runExport('obsidian')} disabled={exporting} className="btn-ghost disabled:opacity-40">
              Obsidian vault…
            </button>
            <button onClick={() => runExport('file')} disabled={exporting} className="btn-ghost disabled:opacity-40">
              Plain file…
            </button>
          </div>
          <div className="border-t border-white/5 pt-3">
            <p className="mb-2 text-sm text-text-tertiary">
              Notion — paste an internal-integration token and a page ID it can access.
            </p>
            <input
              value={notionToken}
              onChange={(e) => setNotionToken(e.target.value)}
              placeholder="Notion integration token (secret_…)"
              className="glass-subtle mb-2 w-full rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
            />
            <input
              value={notionPage}
              onChange={(e) => setNotionPage(e.target.value)}
              placeholder="Parent page ID"
              className="glass-subtle mb-2 w-full rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
            />
            <button onClick={() => runExport('notion')} disabled={exporting} className="btn-ghost disabled:opacity-40">
              {exporting ? 'Exporting…' : 'Export to Notion'}
            </button>
          </div>
        </div>
      </SettingRow>

      <SettingRow
        icon={Wrench}
        title="Memory maintenance"
        subtitle="Find and remove legacy app/file-index memories (these belong in the knowledge graph, not memories). Analyze is read-only."
        keywords="maintenance cleanup delete app file index memories audit"
      >
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <button onClick={auditMemories} disabled={memAuditing || memDeleting} className="btn-ghost disabled:opacity-40">
              {memAuditing ? 'Analyzing…' : 'Analyze memories'}
            </button>
            {memBreakdown && memBreakdown.appIndexCount > 0 && (
              <button onClick={deleteAppIndexMemories} disabled={memDeleting || memAuditing} className="btn-primary px-4 py-2 disabled:opacity-40">
                {memDeleting
                  ? `Deleting ${memDeleteProgress}/${memBreakdown.appIndexCount}…`
                  : `Delete ${memBreakdown.appIndexCount} app/file memories`}
              </button>
            )}
          </div>
          {memBreakdown && (
            <div className="glass-subtle rounded-lg px-4 py-3 text-sm text-text-tertiary">
              <p className="mb-2 text-text-secondary">
                {memBreakdown.total} total memories ·{' '}
                <span className="text-text-primary">{memBreakdown.appIndexCount}</span> app/file-index matches
              </p>
              {memBreakdown.appIndexCount > 0 && (
                <ul className="mb-3 max-h-32 overflow-y-auto">
                  {memBreakdown.appIndexSamples.map((s, i) => (
                    <li key={i} className="py-0.5">• {s}</li>
                  ))}
                </ul>
              )}
              <p className="mb-1 text-text-secondary">Breakdown by tag (not deleted):</p>
              <ul className="max-h-40 overflow-y-auto">
                {memBreakdown.groups.map((g) => (
                  <li key={g.key} className="py-0.5">
                    <span className="text-text-primary">{g.count}</span> — {g.key}
                    {g.samples[0] ? <span className="opacity-60"> · e.g. “{g.samples[0]}”</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </SettingRow>

      {/* Integrations (Sticky Notes, Google) live under Advanced. */}
      <IntegrationsTab />

      <SettingRow
        icon={FolderSearch}
        title="File indexing"
        subtitle={
          fileIndex
            ? `${fileIndex.filesIndexed.toLocaleString()} items indexed${
                fileIndex.lastRunAt ? ` · last run ${new Date(fileIndex.lastRunAt).toLocaleString()}` : ''
              }`
            : 'Indexes file names/metadata locally (contents never read or uploaded).'
        }
        keywords="file index scan rescan local"
        control={
          <button onClick={rescan} disabled={scanning} className="btn-ghost disabled:opacity-40">
            {scanning ? 'Indexing…' : 'Re-scan now'}
          </button>
        }
      />

      <SettingRow
        icon={Network}
        title="Knowledge graph"
        subtitle={
          kgStatus
            ? `${kgStatus.nodeCount.toLocaleString()} nodes · ${kgStatus.edgeCount.toLocaleString()} relationships${
                kgStatus.lastBuiltAt ? ` · last built ${new Date(kgStatus.lastBuiltAt).toLocaleString()}` : ''
              }`
            : 'A local graph of your projects, tech, people, and apps — used to ground chat answers.'
        }
        keywords="knowledge graph rebuild kg nodes"
        control={
          <button onClick={rebuildKg} disabled={rebuildingKg} className="btn-ghost disabled:opacity-40">
            {rebuildingKg ? 'Rebuilding…' : 'Rebuild now'}
          </button>
        }
      />

      <SettingRow
        icon={RotateCcw}
        title="Replay onboarding"
        subtitle="Run the startup wizard again from the beginning."
        keywords="onboarding wizard replay reset"
        control={
          <button onClick={replayOnboarding} className="btn-ghost">
            Replay
          </button>
        }
      />
    </>
  )
}
