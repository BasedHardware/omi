/**
 * Write-ahead log model for captured audio — Windows port of the Flutter
 * `services/wals/wal.dart` model (the protocol authority) and the desktop
 * shape in macOS `OmiWAL/WALModel.swift`.
 *
 * A WAL entry is one recording that the live transcription socket did not
 * take: the audio is kept on disk and uploaded later so it still becomes a
 * conversation. Shared between main (which owns the files and the uploads) and
 * the renderer (which renders sync state), so it lives in shared/.
 */

/**
 * Sync lifecycle of a recording.
 *
 * - `inProgress` — still being written (audio is live).
 * - `miss`       — finalized locally, not yet uploaded (or reverted to retry).
 * - `uploaded`   — the server accepted the bytes (HTTP 202) and its job is
 *                  running. NOT confirmed and NOT deletable: the local file is
 *                  retained until `synced`, because a job can still fail.
 * - `synced`     — the job confirmed success and the conversation exists. Safe
 *                  to clean up.
 * - `corrupted`  — the local file is missing or unreadable.
 * - `outsideRecoveryWindow` — the server permanently refused the recording for
 *                  being older than the automatic-recovery window (HTTP 422
 *                  `backfill_lookback_exceeded`). The file is kept, but
 *                  re-uploading can never succeed, so sync is terminal.
 */
export type WalStatus =
  | 'inProgress'
  | 'miss'
  | 'uploaded'
  | 'synced'
  | 'corrupted'
  | 'outsideRecoveryWindow'

/** Where the recording's bytes live. */
export type WalStorage = 'mem' | 'disk'

/**
 * User-facing sync state for one recording, derived from status, isSyncing and
 * retryCount. The UI renders an explicit label for every value so a recording
 * that has not synced yet never looks identical to one that failed.
 */
export type WalSyncDisplayState =
  | 'syncing'
  | 'uploaded'
  | 'synced'
  | 'waiting'
  | 'retrying'
  | 'failed'
  | 'corrupted'
  | 'outsideRecoveryWindow'

/** Automatic attempts before a recording is presented as failed. */
export const WAL_MAX_AUTO_RETRIES = 3

/** Seconds of audio per stored chunk. */
export const WAL_CHUNK_SECONDS = 60
/** How often finished chunks are flushed from memory to disk. */
export const WAL_FLUSH_INTERVAL_SECONDS = 90
/**
 * How far behind the present the chunker judges frames. Recent frames may still
 * be acknowledged, so judging them immediately would store audio the socket was
 * about to take.
 */
export const WAL_NEW_FRAME_SYNC_DELAY_SECONDS = 15
/** Seconds of unacknowledged audio in a chunk before it is worth storing. */
export const WAL_LOSS_THRESHOLD_SECONDS = 10

export interface WalEntry {
  /** Capture start, unix seconds. Also the timestamp in the upload filename. */
  timerStart: number
  /** Wire codec of the stored frames. */
  codec: string
  channel: number
  sampleRate: number
  /** Duration of the recording in seconds. */
  seconds: number
  /** Capture source id ("phone" on mobile; the desktop uses the audio source). */
  device: string
  deviceModel: string | null
  status: WalStatus
  storage: WalStorage
  /** File name (not a full path) once flushed to disk. */
  filePath: string | null
  frameSize: number
  totalFrames: number
  /** Leading run of frames the live socket already took. */
  syncedFrameOffset: number
  /** Set when the recording belongs to a conversation created live. */
  conversationId: string | null
  retryCount: number
  /** Unix seconds of the last attempt. */
  lastRetryAt: number
  /** Server job id from the 202. Shared by every entry in one upload batch. */
  jobId: string | null
  /** Unix seconds when the 202 was received. */
  uploadedAt: number
  /** Bytes on disk, for the UI and the retention budget. */
  sizeBytes: number
}

export interface WalEntryInit {
  timerStart: number
  codec: string
  seconds: number
  frameSize: number
  totalFrames: number
  sampleRate?: number
  channel?: number
  device?: string
  deviceModel?: string | null
  status?: WalStatus
  storage?: WalStorage
  filePath?: string | null
  syncedFrameOffset?: number
  conversationId?: string | null
  retryCount?: number
  lastRetryAt?: number
  jobId?: string | null
  uploadedAt?: number
  sizeBytes?: number
}

export function makeWalEntry(init: WalEntryInit): WalEntry {
  return {
    timerStart: init.timerStart,
    codec: init.codec,
    channel: init.channel ?? 1,
    sampleRate: init.sampleRate ?? 16_000,
    seconds: init.seconds,
    device: init.device ?? 'phone',
    deviceModel: init.deviceModel ?? null,
    status: init.status ?? 'inProgress',
    storage: init.storage ?? 'mem',
    filePath: init.filePath ?? null,
    frameSize: init.frameSize,
    totalFrames: init.totalFrames,
    syncedFrameOffset: init.syncedFrameOffset ?? 0,
    conversationId: init.conversationId ?? null,
    retryCount: init.retryCount ?? 0,
    lastRetryAt: init.lastRetryAt ?? 0,
    jobId: init.jobId ?? null,
    uploadedAt: init.uploadedAt ?? 0,
    sizeBytes: init.sizeBytes ?? 0
  }
}

/** Stable identity: one recording per capture source per start time. */
export function walId(entry: Pick<WalEntry, 'device' | 'timerStart'>): string {
  return `${entry.device}_${entry.timerStart}`
}

/**
 * The single source of truth for how a recording is shown. Terminal states win
 * first: a stale isSyncing flag left by an interrupted attempt must never
 * present a corrupted or permanently refused recording as an active upload.
 */
export function walSyncDisplayState(
  entry: Pick<WalEntry, 'status' | 'retryCount'>,
  isSyncing: boolean
): WalSyncDisplayState {
  if (entry.status === 'corrupted') return 'corrupted'
  if (entry.status === 'outsideRecoveryWindow') return 'outsideRecoveryWindow'
  if (isSyncing) return 'syncing'
  switch (entry.status) {
    case 'uploaded':
      return 'uploaded'
    case 'synced':
      return 'synced'
    case 'miss':
      if (entry.retryCount >= WAL_MAX_AUTO_RETRIES) return 'failed'
      if (entry.retryCount > 0) return 'retrying'
      return 'waiting'
    case 'inProgress':
      return 'waiting'
  }
}

/** True while the recording still needs an upload attempt. */
export function isWalPending(entry: Pick<WalEntry, 'status'>): boolean {
  return entry.status === 'miss' || entry.status === 'inProgress'
}

/** True once the local bytes can be deleted. Deliberately excludes `uploaded`:
 *  the server has the bytes but has not confirmed the conversation yet. */
export function isWalDeletable(entry: Pick<WalEntry, 'status'>): boolean {
  return entry.status === 'synced'
}

// --- upload filename contract -----------------------------------------------

/** Device segment of the filename: alphanumerics only, lowercased. */
export function sanitizeWalDevice(device: string): string {
  return device.replace(/[^a-zA-Z0-9]/g, '').toLowerCase()
}

/**
 * Upload file name. The backend parses the capture time from the text after
 * the LAST underscore, so the timestamp must stay in that position:
 * `audio_{device}_{codec}_{sampleRate}_{channel}_fs{frameSize}_{timerStart}.bin`
 */
export function walFileName(
  entry: Pick<WalEntry, 'device' | 'codec' | 'sampleRate' | 'channel' | 'frameSize' | 'timerStart'>
): string {
  const device = sanitizeWalDevice(entry.device)
  return `audio_${device}_${entry.codec}_${entry.sampleRate}_${entry.channel}_fs${entry.frameSize}_${entry.timerStart}.bin`
}

/**
 * Capture time a server would read out of a name, mirroring the backend's
 * `parse_sync_filename_timestamp`: take the text after the last underscore,
 * drop the extension, and treat values above 10_000_000_000 as milliseconds.
 * Returns null when the name carries no usable timestamp, which is exactly
 * when the upload would be classified as untrusted backfill.
 */
export function parseWalFileNameTimestamp(name: string): number | null {
  const fileName = name.split('/').pop() ?? name
  const afterUnderscore = fileName.includes('_')
    ? fileName.slice(fileName.lastIndexOf('_') + 1)
    : fileName
  const withoutExtension = afterUnderscore.includes('.')
    ? afterUnderscore.slice(0, afterUnderscore.lastIndexOf('.'))
    : afterUnderscore
  if (withoutExtension.length === 0) return null
  const raw = Number(withoutExtension)
  if (!Number.isFinite(raw) || raw <= 0) return null
  const seconds = raw > 10_000_000_000 ? raw / 1000 : raw
  if (!Number.isFinite(seconds) || seconds <= 0) return null
  return seconds
}
