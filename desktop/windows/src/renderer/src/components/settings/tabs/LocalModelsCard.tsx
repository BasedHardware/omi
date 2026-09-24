import { useCallback, useEffect, useState } from 'react'
import { Download, Trash2, X, Check, Loader2, Cpu } from 'lucide-react'
import type { ModelEntry, ModelStatus, ModelDownloadProgress } from '../../../../../shared/types'
import { formatBytes, downloadPct, actionLabel } from '../../../lib/localModelsUi'

/**
 * Settings → Agents → Local models. Lists the curated local models and lets a
 * user download/resume/delete one. The heavy lifting (HF-cache dedupe, resume,
 * sha256 verify) is the main-process model store (#15948); this card is just the
 * surface + a live progress bar driven by `models:progress`.
 */

type Row = {
  entry: ModelEntry
  status: ModelStatus['state']
  bytesOnDisk: number
  progress: ModelDownloadProgress | null
}

export function LocalModelsCard(): React.JSX.Element {
  const [rows, setRows] = useState<Row[]>([])
  const [deviceRamGb, setDeviceRamGb] = useState<number | undefined>(undefined)

  const load = useCallback(async (): Promise<void> => {
    // Defensive: the manager IPC may be absent in older builds / partial test
    // stubs. Degrade to an empty list rather than throwing during render/effects.
    const omi = window.omi as Partial<typeof window.omi>
    if (!omi.modelsList || !omi.modelsStatus) return
    const [entries, statuses] = await Promise.all([omi.modelsList(), omi.modelsStatus()])
    const byId = new Map(statuses.map((s) => [s.entry.id, s]))
    setRows(
      entries.map((entry) => {
        const s = byId.get(entry.id)
        return {
          entry,
          status: s?.state ?? 'absent',
          bytesOnDisk: s?.bytesOnDisk ?? 0,
          progress: null
        }
      })
    )
  }, [])

  useEffect(() => {
    // load() is async — its setRows lands after an await, not synchronously in
    // this effect body (the rule flags the transitive call as a false positive).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load()
    // Unsubscribe onModelsProgress on cleanup (no leak on remount / StrictMode).
    const off = (window.omi as Partial<typeof window.omi>).onModelsProgress?.((p) => {
      setRows((prev) =>
        prev.map((r) =>
          r.entry.id === p.id
            ? { ...r, progress: p, status: p.phase === 'done' ? 'installed' : r.status }
            : r
        )
      )
    })
    return off
  }, [load])

  // Best-effort RAM read for the advisory only; absence just hides the warning.
  useEffect(() => {
    ;(window.omi as unknown as { systemMemoryGb?: () => Promise<number> })
      .systemMemoryGb?.()
      .then((gb) => setDeviceRamGb(gb))
      .catch(() => setDeviceRamGb(undefined))
  }, [])

  const download = async (id: string): Promise<void> => {
    setRows((prev) =>
      prev.map((r) =>
        r.entry.id === id ? { ...r, progress: { id, received: 0, total: 0, phase: 'download' } } : r
      )
    )
    await window.omi.modelsDownload(id)
    await load()
  }
  const cancel = (id: string): void => void window.omi.modelsCancel(id)
  const del = async (id: string): Promise<void> => {
    await window.omi.modelsDelete(id)
    await load()
  }

  return (
    <div className="mt-6">
      <h3 className="mb-1 flex items-center gap-2 font-semibold text-text-primary">
        <Cpu className="h-4 w-4" /> Local models
      </h3>
      <p className="mb-3 text-sm text-text-tertiary">
        Download a model once and Omi can run turns fully on your machine. Files already in your
        Hugging Face cache are reused (no re-download).
      </p>
      <div className="flex flex-col gap-3">
        {rows.map((r) => {
          const busy =
            r.progress &&
            r.progress.phase !== 'done' &&
            r.progress.phase !== 'error' &&
            r.progress.phase !== 'cancelled'
          const pct = r.progress
            ? downloadPct(r.progress.received, r.progress.total || r.entry.sizeBytes)
            : 0
          return (
            <div key={r.entry.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-text-primary">
                    {r.entry.label}
                  </div>
                  <div className="text-xs text-text-tertiary">
                    {formatBytes(r.entry.sizeBytes)}
                    {r.entry.vision ? ' · vision' : ''}
                    {r.entry.minRamGb ? ` · needs ≥ ${r.entry.minRamGb} GB RAM` : ''}
                  </div>
                  {r.status === 'installed' && (
                    <div className="mt-0.5 flex items-center gap-1 text-xs text-emerald-400">
                      <Check className="h-3 w-3" /> Installed
                    </div>
                  )}
                  {deviceRamGb !== undefined &&
                    r.entry.minRamGb &&
                    deviceRamGb < r.entry.minRamGb && (
                      <div className="mt-0.5 text-xs text-amber-400">
                        This machine has ~{Math.round(deviceRamGb)} GB — below this model’s
                        recommendation.
                      </div>
                    )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {r.status === 'installed' ? (
                    <button
                      onClick={() => void del(r.entry.id)}
                      title="Delete"
                      className="rounded-md bg-white/5 p-2 text-text-tertiary hover:text-white"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  ) : busy ? (
                    <button
                      onClick={() => cancel(r.entry.id)}
                      title="Cancel"
                      className="rounded-md bg-white/5 p-2 text-text-tertiary hover:text-white"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  ) : (
                    <button
                      onClick={() => void download(r.entry.id)}
                      className="flex items-center gap-1.5 rounded-md bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/20"
                    >
                      <Download className="h-4 w-4" /> {actionLabel(r.status)}
                    </button>
                  )}
                </div>
              </div>
              {busy && (
                <div className="mt-2">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-sky-400 transition-[width]"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <div className="mt-1 flex items-center gap-1 text-xs text-text-tertiary">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {r.progress?.phase === 'verify'
                      ? 'Verifying…'
                      : r.progress?.phase === 'cache'
                        ? 'Using local cache…'
                        : `${pct}%`}
                  </div>
                  {r.progress?.phase === 'error' && (
                    <div className="mt-1 text-xs text-red-400">{r.progress.error}</div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
