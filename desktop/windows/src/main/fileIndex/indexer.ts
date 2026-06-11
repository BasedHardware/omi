import { promises as fs, existsSync, type Dirent } from 'fs'
import { basename, extname, join } from 'path'
import { shell } from 'electron'
import { resolveScanRoots } from './scanRoots'
import { shouldVisitDir, shouldIndexFile, MAX_DEPTH } from './scanRules'
import { categorizeExtension } from './fileTypes'
import { replaceIndexedFiles, clearIndexedFiles, getFileIndexStats } from '../ipc/db'
import type { IndexedFileRecord, FileIndexStatus } from '../../shared/types'

let running = false
let lastRunAt: number | null = null
let lastDurationMs: number | null = null

async function readDir(dir: string): Promise<Dirent[]> {
  try {
    return await fs.readdir(dir, { withFileTypes: true })
  } catch {
    return [] // unreadable/permission-denied dirs are skipped
  }
}

// Walk a 'files' root, recording metadata for each file within depth/size rules.
async function walkFiles(root: string, out: IndexedFileRecord[]): Promise<void> {
  const recurse = async (dir: string, depth: number): Promise<void> => {
    for (const ent of await readDir(dir)) {
      const full = join(dir, ent.name)
      if (ent.isDirectory()) {
        if (shouldVisitDir(ent.name, depth + 1)) await recurse(full, depth + 1)
      } else if (ent.isFile()) {
        try {
          const st = await fs.stat(full)
          if (!shouldIndexFile(st.size)) continue
          out.push({
            path: full,
            filename: ent.name,
            extension: extname(ent.name).replace(/^\./, '').toLowerCase(),
            fileType: categorizeExtension(extname(ent.name)),
            sizeBytes: st.size,
            folder: dir,
            depth,
            createdAt: Math.round(st.birthtimeMs),
            modifiedAt: Math.round(st.mtimeMs)
          })
        } catch {
          /* skip unreadable file */
        }
      }
    }
  }
  await recurse(root, 0)
}

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

// Walk a Start-Menu root: each .lnk shortcut is one installed app
// (the Windows analog of a macOS /Applications .app bundle).
async function walkApps(root: string, out: IndexedFileRecord[]): Promise<void> {
  const recurse = async (dir: string, depth: number): Promise<void> => {
    if (depth > MAX_DEPTH) return
    for (const ent of await readDir(dir)) {
      const full = join(dir, ent.name)
      if (ent.isDirectory()) {
        await recurse(full, depth + 1)
      } else if (ent.isFile() && ent.name.toLowerCase().endsWith('.lnk')) {
        try {
          const st = await fs.stat(full)
          out.push({
            path: full,
            filename: basename(ent.name, '.lnk'),
            extension: 'lnk',
            fileType: 'application',
            sizeBytes: st.size,
            folder: dir,
            depth,
            createdAt: Math.round(st.birthtimeMs),
            modifiedAt: Math.round(st.mtimeMs),
            targetPath: resolveShortcutTarget(full)
          })
        } catch {
          /* skip */
        }
      }
    }
  }
  await recurse(root, 0)
}

export function getStatus(): FileIndexStatus {
  const { filesIndexed, byType } = getFileIndexStats()
  return { filesIndexed, byType, lastRunAt, lastDurationMs, running }
}

// Full re-scan: collect all records, then atomically replace the table.
export async function runFileIndex(): Promise<FileIndexStatus> {
  if (running) return getStatus()
  running = true
  const t0 = Date.now()
  try {
    const records: IndexedFileRecord[] = []
    for (const r of resolveScanRoots(
      { USERPROFILE: process.env.USERPROFILE, ProgramData: process.env.ProgramData, APPDATA: process.env.APPDATA },
      existsSync
    )) {
      if (r.kind === 'apps') await walkApps(r.path, records)
      else await walkFiles(r.path, records)
    }
    clearIndexedFiles()
    replaceIndexedFiles(records)
    lastRunAt = Date.now()
    lastDurationMs = lastRunAt - t0
    return getStatus()
  } finally {
    running = false
  }
}
