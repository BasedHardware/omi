/**
 * Owns offline-audio capture in the running app: the folder the audio lives in,
 * the timers that judge and upload it, and the IPC the UI reads it through.
 *
 * The schedule mirrors the Flutter service. Judging runs on a chunk-plus-delay
 * cadence, uploads and job reconciliation run on their own timers, and
 * retention runs rarely because it only ever releases confirmed audio.
 */

import { ipcMain, app, type WebContents } from 'electron'
import { join } from 'path'
import { mkdirSync, existsSync } from 'fs'
import { readFile, writeFile, unlink, stat } from 'fs/promises'
import {
  WAL_CHUNK_SECONDS,
  WAL_NEW_FRAME_SYNC_DELAY_SECONDS,
  walId,
  walSyncDisplayState
} from '../../shared/wal'
import type { WalSyncSnapshot } from '../../shared/types'
import { WalCapture } from './walCapture'
import { WalSyncEngine } from './syncEngine'
import { WalHttpClient } from './walHttp'
import { planRetention, DEFAULT_RETENTION, type RetentionPolicy } from './walRetention'
import {
  cleanupCandidates,
  deleteWal,
  getWal,
  listWals,
  resetWalRetries,
  walStats,
  type WalDb
} from './walStore'

const FLUSH_INTERVAL_MS = (WAL_CHUNK_SECONDS + WAL_NEW_FRAME_SYNC_DELAY_SECONDS) * 1000
const SYNC_INTERVAL_MS = 60_000
const RECONCILE_INTERVAL_MS = 30_000
const RETENTION_INTERVAL_MS = 60 * 60_000
const WAL_DIRECTORY = 'wal-audio'

export interface WalServiceOptions {
  db: WalDb
  getToken: () => Promise<string | null>
  /** Null until a session has run; the client defers rather than sending an
   *  upload the backend cannot bind to this install. */
  getDeviceIdHash: () => Promise<string | null>
  baseUrl: string
  appVersion: string
  /** Reads the user's offline-capture preferences. */
  settings: () => { autoSync: boolean; retainEverything: boolean; retention: RetentionPolicy }
  /** UI windows to notify when the log changes. */
  broadcast: (snapshot: WalSyncSnapshot) => void
}

export class WalService {
  private readonly directory: string
  private readonly capture: WalCapture
  private readonly engine: WalSyncEngine
  private timers: Array<ReturnType<typeof setInterval>> = []
  private started = false

  constructor(private readonly options: WalServiceOptions) {
    this.directory = join(app.getPath('userData'), WAL_DIRECTORY)
    if (!existsSync(this.directory)) mkdirSync(this.directory, { recursive: true })

    this.capture = new WalCapture({
      db: options.db,
      writeFile: async (fileName, bytes) => {
        await writeFile(join(this.directory, fileName), bytes)
        return bytes.byteLength
      },
      now: () => Date.now(),
      storeEverything: () => options.settings().retainEverything,
      onStored: () => this.publish()
    })

    const http = new WalHttpClient({
      baseUrl: options.baseUrl,
      getToken: options.getToken,
      getDeviceIdHash: options.getDeviceIdHash,
      appVersion: options.appVersion
    })

    this.engine = new WalSyncEngine({
      db: options.db,
      http,
      readFile: async (fileName) => {
        try {
          return new Uint8Array(await readFile(join(this.directory, fileName)))
        } catch {
          return null
        }
      },
      deleteFile: async (fileName) => {
        try {
          await unlink(join(this.directory, fileName))
        } catch {
          // Already gone is the desired end state.
        }
      },
      fileExists: (fileName) => existsSync(join(this.directory, fileName)),
      nowSeconds: () => Math.floor(Date.now() / 1000),
      onChange: () => this.publish()
    })
  }

  /** The observer omiListen reports fed-chunk dispositions to. */
  get feedObserver(): {
    observe: (args: {
      source: 'mic' | 'system'
      bytes: Uint8Array
      byteLength: number
      disposition: 'sent' | 'buffered' | 'missed'
      conversationId?: string | null
    }) => void
    resolveBuffered: (
      source: 'mic' | 'system',
      disposition: 'sent' | 'missed',
      count?: number
    ) => void
  } {
    return {
      observe: (args) => this.capture.observe(args),
      resolveBuffered: (source, disposition, count) => {
        this.capture.resolveBuffered(source, disposition, count)
      }
    }
  }

  start(): void {
    if (this.started) return
    this.started = true
    const every = (ms: number, run: () => void): void => {
      const timer = setInterval(run, ms)
      // Never keep the process alive just to service the log.
      timer.unref?.()
      this.timers.push(timer)
    }
    every(FLUSH_INTERVAL_MS, () => void this.capture.flushAll())
    every(SYNC_INTERVAL_MS, () => void this.runSyncPass())
    every(RECONCILE_INTERVAL_MS, () => void this.engine.reconcileUploaded())
    every(RETENTION_INTERVAL_MS, () => void this.applyRetention())
  }

  async stop(): Promise<void> {
    for (const timer of this.timers) clearInterval(timer)
    this.timers = []
    this.started = false
    // Audio still in memory at shutdown is written rather than lost.
    await this.capture.drainAll()
  }

  private async runSyncPass(): Promise<void> {
    if (!this.options.settings().autoSync) return
    await this.engine.syncPending()
  }

  private async applyRetention(): Promise<void> {
    const entries = listWals(this.options.db)
    const plan = planRetention(
      entries,
      this.options.settings().retention ?? DEFAULT_RETENTION,
      Math.floor(Date.now() / 1000)
    )
    const releasable = [...plan.expired, ...plan.overBudget]
    if (releasable.length === 0) {
      if (plan.atCapacity) {
        console.warn(
          '[wal] offline audio is at capacity and the rest is unconfirmed; not deleting it'
        )
      }
      return
    }
    await this.engine.cleanupConfirmed(releasable)
    for (const entry of releasable) deleteWal(this.options.db, walId(entry))
    this.publish()
  }

  /** Sign-out: buffered audio belongs to the account that captured it. */
  reset(): void {
    this.capture.reset()
    this.engine.resume()
  }

  snapshot(): WalSyncSnapshot {
    const entries = listWals(this.options.db)
    return {
      stats: walStats(this.options.db),
      paused: this.engine.isPaused,
      recordings: entries.map((entry) => ({
        id: walId(entry),
        timerStart: entry.timerStart,
        seconds: entry.seconds,
        device: entry.device,
        sizeBytes: entry.sizeBytes,
        state: walSyncDisplayState(entry, false),
        retryCount: entry.retryCount
      }))
    }
  }

  private publish(): void {
    this.options.broadcast(this.snapshot())
  }

  /** Manual retry from the UI: clears the attempt history and runs a pass. */
  async retry(id: string): Promise<void> {
    const entry = getWal(this.options.db, id)
    if (entry === null) return
    // A recording with no bytes cannot be retried into existence.
    if (entry.filePath === null || !existsSync(join(this.directory, entry.filePath))) return
    resetWalRetries(this.options.db, id)
    this.engine.resume()
    this.publish()
    await this.engine.syncPending()
  }

  /** Deletes one recording and its audio at the user's request. */
  async discard(id: string): Promise<void> {
    const entry = getWal(this.options.db, id)
    if (entry === null) return
    if (entry.filePath !== null) {
      try {
        await unlink(join(this.directory, entry.filePath))
      } catch {
        // Already gone.
      }
    }
    deleteWal(this.options.db, id)
    this.publish()
  }

  /** Bytes currently on disk, for the settings summary. */
  async storageBytes(): Promise<number> {
    const entries = listWals(this.options.db)
    let bytes = 0
    for (const entry of entries) {
      if (entry.filePath === null) continue
      try {
        bytes += (await stat(join(this.directory, entry.filePath))).size
      } catch {
        // Counted as zero; the reconciler will mark it corrupted.
      }
    }
    return bytes
  }

  /** Releases everything the server confirmed, on demand. */
  async releaseConfirmed(): Promise<number> {
    const candidates = cleanupCandidates(this.options.db, Math.floor(Date.now() / 1000))
    const removed = await this.engine.cleanupConfirmed(candidates)
    for (const entry of candidates) deleteWal(this.options.db, walId(entry))
    this.publish()
    return removed
  }
}

/** Wires the renderer-facing surface. Reads are open; actions are main-window
 *  only, matching how the rest of the app gates destructive controls. */
export function registerWalHandlers(
  getService: () => WalService | null,
  getMainWcId: () => number | undefined
): void {
  const fromMainWindow = (event: { sender: WebContents }): boolean => {
    const mainId = getMainWcId()
    return mainId !== undefined && event.sender.id === mainId
  }

  ipcMain.handle('omi-wal:snapshot', () => getService()?.snapshot() ?? null)
  ipcMain.handle('omi-wal:storage-bytes', async () => (await getService()?.storageBytes()) ?? 0)
  ipcMain.handle('omi-wal:retry', async (e, id: string) => {
    if (!fromMainWindow(e)) return
    await getService()?.retry(id)
  })
  ipcMain.handle('omi-wal:discard', async (e, id: string) => {
    if (!fromMainWindow(e)) return
    await getService()?.discard(id)
  })
  ipcMain.handle('omi-wal:release-confirmed', async (e) => {
    if (!fromMainWindow(e)) return 0
    return (await getService()?.releaseConfirmed()) ?? 0
  })
}
