/**
 * Uploads recordings the transcription socket did not take, and resolves the
 * jobs that own them. Orchestration only: every decision lives in syncPolicy so
 * the wire contract is tested without I/O, and every edge (files, HTTP, clock)
 * is injected so the engine itself is testable without Electron or a network.
 *
 * Shape follows macOS `WAL/WALService.swift` + `WALSyncReconciler.swift`: one
 * batch per pass, one poll per job per pass, and no blocking loops.
 */

import { walFileName, walId, type WalEntry } from '../../shared/wal'
import {
  canAttemptUpload,
  classifyJobStatus,
  classifyUploadResponse,
  nextStatusForJobOutcome,
  type UploadResponseLike
} from './syncPolicy'
import {
  listPendingWals,
  listUploadedWals,
  markMissingFilesCorrupted,
  markWalUploaded,
  recordWalRetry,
  setWalStatus,
  type WalDb
} from './walStore'

export interface WalUploadFile {
  fileName: string
  bytes: Uint8Array
}

export interface WalSyncHttp {
  /** POST /v2/sync-local-files as multipart. */
  uploadFiles(args: {
    files: WalUploadFile[]
    conversationId: string | null
    manifest: string | null
  }): Promise<UploadResponseLike>
  /** GET /v2/sync-local-files/{job_id}. */
  fetchJobStatus(jobId: string): Promise<{ status: number; body?: unknown }>
  /** POST /v2/sync-capture-manifest; null when unavailable, which only costs
   *  the trusted lane, never the upload. */
  requestCaptureManifest(args: {
    files: Array<{ name: string; size: number }>
    conversationId: string | null
  }): Promise<string | null>
}

export interface WalSyncDeps {
  db: WalDb
  http: WalSyncHttp
  readFile: (fileName: string) => Promise<Uint8Array | null>
  deleteFile: (fileName: string) => Promise<void>
  fileExists: (fileName: string) => boolean
  nowSeconds: () => number
  /** Recordings uploaded together in one request. */
  batchSize?: number
  onChange?: () => void
}

export interface SyncPassResult {
  attempted: number
  accepted: number
  deferred: boolean
  /** Set while the backend has asked for a pause. */
  pausedUntilSeconds: number | null
}

const DEFAULT_BATCH_SIZE = 5

export class WalSyncEngine {
  private pausedUntilSeconds: number | null = null
  private running = false

  constructor(private readonly deps: WalSyncDeps) {}

  get isPaused(): boolean {
    if (this.pausedUntilSeconds === null) return false
    return this.deps.nowSeconds() < this.pausedUntilSeconds
  }

  /**
   * One upload pass: take a batch of recordings that are due, send them
   * together, and record what the server said. A batch shares one job id, which
   * is how the reconciler later resolves them together.
   */
  async syncPending(): Promise<SyncPassResult> {
    const idle: SyncPassResult = {
      attempted: 0,
      accepted: 0,
      deferred: false,
      pausedUntilSeconds: this.pausedUntilSeconds
    }
    // One pass at a time: a second would re-send the same batch and create a
    // duplicate conversation from the same audio.
    if (this.running) return { ...idle, deferred: true }
    if (this.isPaused) return { ...idle, deferred: true }
    this.running = true
    try {
      const nowSeconds = this.deps.nowSeconds()
      markMissingFilesCorrupted(this.deps.db, this.deps.fileExists)

      const due = listPendingWals(this.deps.db, (this.deps.batchSize ?? DEFAULT_BATCH_SIZE) * 4)
        .filter((entry) =>
          canAttemptUpload({
            retryCount: entry.retryCount,
            lastRetryAt: entry.lastRetryAt,
            nowSeconds,
            pausedUntilSeconds: this.pausedUntilSeconds ?? undefined
          })
        )
        .slice(0, this.deps.batchSize ?? DEFAULT_BATCH_SIZE)
      if (due.length === 0) return idle

      const loaded: Array<{ entry: WalEntry; file: WalUploadFile }> = []
      for (const entry of due) {
        const fileName = entry.filePath ?? walFileName(entry)
        const bytes = await this.deps.readFile(fileName)
        if (bytes === null) {
          // The index says it exists but the bytes are gone.
          setWalStatus(this.deps.db, walId(entry), 'corrupted')
          continue
        }
        loaded.push({ entry, file: { fileName, bytes } })
      }
      if (loaded.length === 0) {
        this.deps.onChange?.()
        return { ...idle, attempted: 0 }
      }

      // Every recording in a batch must belong to the same conversation, or
      // none: the endpoint attaches the whole upload to one conversation id.
      const conversationIds = new Set(loaded.map((l) => l.entry.conversationId ?? ''))
      const conversationId =
        conversationIds.size === 1 ? (loaded[0].entry.conversationId ?? null) : null

      const manifest = await this.deps.http
        .requestCaptureManifest({
          files: loaded.map((l) => ({ name: l.file.fileName, size: l.file.bytes.byteLength })),
          conversationId
        })
        .catch(() => null)

      const response = await this.deps.http.uploadFiles({
        files: loaded.map((l) => l.file),
        conversationId,
        manifest
      })
      const outcome = classifyUploadResponse(response)
      const ids = loaded.map((l) => walId(l.entry))

      switch (outcome.kind) {
        case 'accepted':
          markWalUploaded(this.deps.db, ids, outcome.jobId, nowSeconds)
          this.deps.onChange?.()
          return { ...idle, attempted: ids.length, accepted: ids.length }
        case 'refusedPermanently':
          // The file stays on disk; only the sync is terminal.
          for (const id of ids) setWalStatus(this.deps.db, id, 'outsideRecoveryWindow')
          this.deps.onChange?.()
          return { ...idle, attempted: ids.length }
        case 'retryAfter':
          this.pausedUntilSeconds = nowSeconds + outcome.seconds
          // Deliberately not a retry: the server refused to look at the audio,
          // so counting an attempt would burn the budget on its capacity.
          this.deps.onChange?.()
          return {
            ...idle,
            attempted: ids.length,
            deferred: true,
            pausedUntilSeconds: this.pausedUntilSeconds
          }
        case 'notAuthorized':
          // A fresh token may fix this; leave the recordings untouched.
          return { ...idle, attempted: ids.length, deferred: true }
        case 'transient':
          for (const id of ids) recordWalRetry(this.deps.db, id, nowSeconds)
          this.deps.onChange?.()
          return { ...idle, attempted: ids.length }
      }
    } finally {
      this.running = false
    }
  }

  /**
   * Resolves recordings whose bytes were accepted: one poll per distinct job,
   * applied to every recording that shares it.
   */
  async reconcileUploaded(): Promise<number> {
    const uploaded = listUploadedWals(this.deps.db)
    if (uploaded.length === 0) return 0

    const byJob = new Map<string, WalEntry[]>()
    for (const entry of uploaded) {
      if (entry.jobId === null) continue
      const members = byJob.get(entry.jobId) ?? []
      members.push(entry)
      byJob.set(entry.jobId, members)
    }

    let changed = 0
    const nowSeconds = this.deps.nowSeconds()
    for (const [jobId, members] of byJob) {
      const response = await this.deps.http.fetchJobStatus(jobId).catch(() => ({ status: 0 }))
      const outcome = classifyJobStatus(response)
      const nextStatus = nextStatusForJobOutcome(outcome)
      if (nextStatus === null) continue
      for (const member of members) {
        const id = walId(member)
        if (nextStatus === 'miss') {
          // Back in the queue with an attempt spent, so a job that keeps
          // failing eventually surfaces to the user instead of looping.
          recordWalRetry(this.deps.db, id, nowSeconds)
        } else {
          setWalStatus(this.deps.db, id, nextStatus)
        }
        changed += 1
      }
    }
    if (changed > 0) this.deps.onChange?.()
    return changed
  }

  /**
   * Releases the bytes of recordings the server confirmed. Only confirmed ones:
   * audio the server holds but has not confirmed is still the only copy.
   */
  async cleanupConfirmed(entries: WalEntry[]): Promise<number> {
    let removed = 0
    for (const entry of entries) {
      if (entry.status !== 'synced') continue
      if (entry.filePath !== null) await this.deps.deleteFile(entry.filePath)
      removed += 1
    }
    if (removed > 0) this.deps.onChange?.()
    return removed
  }

  /** Clears a server-requested pause (used when the user asks to retry now). */
  resume(): void {
    this.pausedUntilSeconds = null
  }
}
