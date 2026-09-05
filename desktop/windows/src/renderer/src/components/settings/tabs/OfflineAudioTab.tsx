// Offline audio settings tab. There is no macOS counterpart: the Mac app keeps
// a write-ahead log but never shows it, so a recording that failed to upload is
// invisible there. On Windows every stored recording gets an explicit state, so
// "not synced yet" never looks the same as "failed".
//
// Machinery: main owns the log (capture has to keep working with no UI open),
// so this tab reads a snapshot over IPC and re-renders on the pushed updates.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { CloudUpload, HardDrive, Archive, RefreshCw, Trash2 } from 'lucide-react'
import type {
  OfflineCaptureSettings,
  WalRecordingView,
  WalSyncSnapshot
} from '../../../../../shared/types'
import { toast } from '../../../lib/toast'
import { formatBytes, formatCapturedAt, formatDuration } from './offlineAudioFormat'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

/** Label and tone for every sync state. A recording is never shown as an
 *  indistinct row: waiting, failed and refused mean different things and offer
 *  different actions. */
const STATE_LABELS: Record<WalRecordingView['state'], { label: string; tone: string }> = {
  syncing: { label: 'Uploading', tone: 'text-text-secondary' },
  uploaded: { label: 'Processing on Omi', tone: 'text-text-secondary' },
  synced: { label: 'Backed up', tone: 'text-emerald-300' },
  waiting: { label: 'Waiting to upload', tone: 'text-text-tertiary' },
  retrying: { label: 'Retrying', tone: 'text-amber-300' },
  failed: { label: 'Upload failed', tone: 'text-amber-300' },
  corrupted: { label: 'Audio file missing', tone: 'text-red-300' },
  outsideRecoveryWindow: { label: 'Too old to recover', tone: 'text-text-tertiary' }
}

const EMPTY: WalSyncSnapshot = {
  stats: { total: 0, pending: 0, uploaded: 0, synced: 0, failed: 0, bytes: 0 },
  paused: false,
  recordings: []
}

export function OfflineAudioTab(): React.JSX.Element {
  const [snapshot, setSnapshot] = useState<WalSyncSnapshot>(EMPTY)
  const [settings, setSettings] = useState<OfflineCaptureSettings | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    void window.omi?.walSnapshot?.().then((s) => s && setSnapshot(s))
    void window.omi?.walGetSettings?.().then((s) => s && setSettings(s))
    return window.omi?.onWalSnapshot?.((next) => setSnapshot(next))
  }, [])

  const patch = useCallback(async (next: Partial<OfflineCaptureSettings>): Promise<void> => {
    setSettings((prev) => (prev === null ? prev : { ...prev, ...next }))
    const saved = await window.omi?.walSetSettings?.(next)
    if (saved) setSettings(saved)
  }, [])

  const retry = async (id: string): Promise<void> => {
    setBusy(id)
    try {
      await window.omi?.walRetry?.(id)
    } finally {
      setBusy(null)
    }
  }

  const discard = async (id: string): Promise<void> => {
    setBusy(id)
    try {
      await window.omi?.walDiscard?.(id)
    } finally {
      setBusy(null)
    }
  }

  const releaseConfirmed = async (): Promise<void> => {
    const removed = (await window.omi?.walReleaseConfirmed?.()) ?? 0
    toast(
      removed === 0
        ? 'Nothing to clear yet'
        : `Cleared ${removed} backed up recording${removed === 1 ? '' : 's'}`
    )
  }

  // Unfinished work first: a person opening this tab is looking for what has
  // not been backed up, not for the archive.
  const ordered = useMemo(() => {
    const rank: Record<WalRecordingView['state'], number> = {
      failed: 0,
      corrupted: 1,
      retrying: 2,
      waiting: 3,
      syncing: 4,
      uploaded: 5,
      outsideRecoveryWindow: 6,
      synced: 7
    }
    return [...snapshot.recordings].sort(
      (a, b) => rank[a.state] - rank[b.state] || b.timerStart - a.timerStart
    )
  }, [snapshot.recordings])

  const { stats } = snapshot

  return (
    <>
      <SettingRow
        icon={CloudUpload}
        dot={stats.pending > 0 ? 'off' : 'on'}
        title="Offline recordings"
        subtitle={
          stats.total === 0
            ? 'When a recording cannot reach Omi, its audio is kept here and uploaded once the connection is back.'
            : `${stats.pending} waiting, ${stats.uploaded} processing, ${stats.synced} backed up. ${formatBytes(stats.bytes)} on disk.`
        }
        keywords="offline sync backup upload recover audio wal recording failed network"
        note={
          snapshot.paused ? (
            <span className="text-amber-300">
              Omi asked to pause uploads for a moment. Your audio is safe and will upload
              automatically.
            </span>
          ) : undefined
        }
      >
        {ordered.length > 0 && (
          <div className="mt-3 space-y-1">
            {ordered.map((recording) => {
              const state = STATE_LABELS[recording.state]
              const canRetry =
                recording.state === 'failed' ||
                recording.state === 'retrying' ||
                recording.state === 'waiting'
              return (
                <div
                  key={recording.id}
                  className="flex items-center justify-between rounded-md bg-white/[0.04] px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <div className="text-white">
                      {formatCapturedAt(recording.timerStart)}
                      <span className="text-text-tertiary">
                        {' '}
                        · {formatDuration(recording.seconds)}
                      </span>
                    </div>
                    <div className={`text-xs ${state.tone}`}>
                      {state.label}
                      {recording.retryCount > 0 && recording.state !== 'synced'
                        ? ` · ${recording.retryCount} attempt${recording.retryCount === 1 ? '' : 's'}`
                        : ''}
                      <span className="text-text-tertiary">
                        {' '}
                        · {formatBytes(recording.sizeBytes)}
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {canRetry && (
                      <button
                        type="button"
                        disabled={busy === recording.id}
                        onClick={() => void retry(recording.id)}
                        className="rounded-md bg-white/10 px-2 py-1 text-xs text-white hover:bg-white/15 disabled:opacity-50"
                        aria-label={`Retry ${recording.id}`}
                      >
                        <RefreshCw className="size-3.5" />
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy === recording.id}
                      onClick={() => void discard(recording.id)}
                      className="rounded-md bg-white/10 px-2 py-1 text-xs text-white hover:bg-white/15 disabled:opacity-50"
                      aria-label={`Delete ${recording.id}`}
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </SettingRow>

      <SettingRow
        icon={RefreshCw}
        dot={settings?.autoSync === false ? 'off' : 'on'}
        title="Upload automatically"
        subtitle="Send kept recordings to Omi on their own. Turn this off to upload only when you ask."
        keywords="auto sync upload automatic offline"
        control={
          <Toggle
            on={settings?.autoSync !== false}
            onChange={(next) => void patch({ autoSync: next })}
            label="Upload automatically"
          />
        }
      />

      <SettingRow
        icon={Archive}
        dot={settings?.retainEverything === true ? 'on' : 'off'}
        title="Keep a copy of everything"
        subtitle="Keep every recording on this machine, not only the ones that could not reach Omi. Uses considerably more disk."
        keywords="archive keep everything local copy storage unlimited"
        control={
          <Toggle
            on={settings?.retainEverything === true}
            onChange={(next) => void patch({ retainEverything: next })}
            label="Keep a copy of everything"
          />
        }
      />

      <SettingRow
        icon={HardDrive}
        title="Storage"
        subtitle={`Backed up recordings are cleared after ${settings?.retentionDays ?? 14} days, or sooner if the log passes ${formatBytes(settings?.maxBytes ?? 0)}. Recordings that are not backed up yet are never deleted to make room.`}
        keywords="storage disk space retention cleanup"
        control={
          <button
            type="button"
            onClick={() => void releaseConfirmed()}
            className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15"
          >
            Clear backed up
          </button>
        }
      />
    </>
  )
}
