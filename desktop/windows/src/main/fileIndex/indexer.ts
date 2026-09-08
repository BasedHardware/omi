import { promises as fs, existsSync } from 'fs'
import { sep } from 'path'
import { shell } from 'electron'
import { resolveScanRoots, candidateScanRoots, type ScanEnv } from './scanRoots'
import { planScan, type ScanFs } from './scanPlan'
import {
  applyFileIndexDiff,
  loadIndexedFileMtimes,
  getFileIndexStats,
  getAppMeta,
  setAppMeta
} from '../ipc/db'
import type { FileIndexStatus } from '../../shared/types'

// app_meta keys — persisted so status survives a restart (the in-memory-only
// values used to reset to null on every launch, making a populated index report
// "never run").
const META_LAST_RUN_AT = 'fileIndex.lastRunAt'
const META_LAST_DURATION_MS = 'fileIndex.lastDurationMs'

let running = false
let startupTimer: ReturnType<typeof setTimeout> | null = null

// Resolve a .lnk to its target executable. Best-effort: returns undefined when
// the shortcut can't be read (e.g. MSIX/UWP shortcuts have no file target).
function resolveShortcutTarget(lnkPath: string): string | undefined {
  try {
    const target = shell.readShortcutLink(lnkPath).target
    return target && target.toLowerCase().endsWith('.exe') ? target : undefined
  } catch {
    return undefined
  }
}

// Real filesystem seam wired into the (electron/db-free, testable) planner.
// readDir rejects on failure so planScan can protect the subtree.
const nodeScanFs: ScanFs = {
  async readDir(dir) {
    const ents = await fs.readdir(dir, { withFileTypes: true })
    return ents.map((e) => ({ name: e.name, isDirectory: e.isDirectory(), isFile: e.isFile() }))
  },
  async stat(path) {
    const st = await fs.stat(path)
    return { size: st.size, birthtimeMs: st.birthtimeMs, mtimeMs: st.mtimeMs }
  },
  resolveShortcutTarget
}

function scanEnv(): ScanEnv {
  return {
    USERPROFILE: process.env.USERPROFILE,
    ProgramData: process.env.ProgramData,
    APPDATA: process.env.APPDATA
  }
}

function numMeta(key: string): number | null {
  const v = getAppMeta(key)
  return v == null ? null : Number(v)
}

export function getStatus(): FileIndexStatus {
  const { filesIndexed, byType } = getFileIndexStats()
  return {
    filesIndexed,
    byType,
    lastRunAt: numMeta(META_LAST_RUN_AT),
    lastDurationMs: numMeta(META_LAST_DURATION_MS),
    running
  }
}

// Re-scan: walk the roots, diff against the existing index, and apply the diff
// atomically. Unlike the previous clear-then-insert, this NEVER blindly wipes the
// table — a root that fails to enumerate (permission blip, AV lock) or is absent
// (unmounted drive) has its subtree protected, so its rows are kept rather than
// purged (ports macOS FileIndexerService.scanFolders).
export async function runFileIndex(): Promise<FileIndexStatus> {
  if (running) return getStatus()
  running = true
  const t0 = Date.now()
  try {
    const env = scanEnv()
    const existing = loadIndexedFileMtimes()
    const absentRootPaths = candidateScanRoots(env)
      .filter((c) => !existsSync(c.path))
      .map((c) => c.path)
    const roots = resolveScanRoots(env, existsSync)

    const plan = await planScan({ roots, absentRootPaths, existing, fs: nodeScanFs, sep })
    applyFileIndexDiff(plan.toUpsert, plan.toDelete)

    const finishedAt = Date.now()
    setAppMeta(META_LAST_RUN_AT, String(finishedAt))
    setAppMeta(META_LAST_DURATION_MS, String(finishedAt - t0))
    return getStatus()
  } finally {
    running = false
  }
}

// Existing-user startup backfill: after launch, refresh the index ONCE so files
// created/deleted while the app was closed are reflected. Gated on an
// already-populated index so a brand-new user's files are never scanned before
// the onboarding consent step runs its first scan. Cheap now that rescans are
// incremental (unchanged rows are not rewritten) and safe (the retention diff
// won't purge on a transient read failure). unref()'d so it never holds the
// process open; cancelable on quit.
export function scheduleStartupRescan(delayMs = 30_000): void {
  if (startupTimer) return
  startupTimer = setTimeout(() => {
    startupTimer = null
    try {
      if (getFileIndexStats().filesIndexed > 0) void runFileIndex().catch(() => {})
    } catch {
      /* never let a backfill failure crash startup */
    }
  }, delayMs)
  startupTimer.unref?.()
}

export function cancelStartupRescan(): void {
  if (startupTimer) {
    clearTimeout(startupTimer)
    startupTimer = null
  }
}
