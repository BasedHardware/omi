import { basename, extname, join } from 'path'
import { shouldVisitDir, shouldIndexFile, isHiddenEntry, pathsToDelete, MAX_DEPTH } from './scanRules'
import { categorizeExtension } from './fileTypes'
import type { ScanRoot } from './scanRoots'
import type { IndexedFileRecord } from '../../shared/types'

// Minimal filesystem surface the planner needs. Injected so the retention /
// fail-open logic is testable without a real filesystem or the Electron-ABI
// better-sqlite3 native module (which plain-node vitest cannot load). The real
// implementation lives in indexer.ts; tests pass a fully in-memory fake.
export type ScanDirEntry = { name: string; isDirectory: boolean; isFile: boolean }
export type ScanStat = { size: number; birthtimeMs: number; mtimeMs: number }
export type ScanFs = {
  // MUST reject to signal an enumeration failure — that is how a directory is
  // marked protected (its previously-indexed rows are kept, not purged).
  readDir(dir: string): Promise<ScanDirEntry[]>
  stat(path: string): Promise<ScanStat>
  // Best-effort .lnk → target .exe resolution (Electron shell in production).
  resolveShortcutTarget(lnkPath: string): string | undefined
}

export type ScanPlan = {
  // New or changed records to upsert.
  toUpsert: IndexedFileRecord[]
  // Previously-indexed paths that are genuinely gone (safe to delete).
  toDelete: string[]
  // Directories/roots whose enumeration failed or were absent (subtree protected).
  failedPrefixes: string[]
}

export type PlanScanOptions = {
  roots: ScanRoot[]
  // Candidate roots that do NOT currently exist (e.g. an unmounted drive). Their
  // subtrees are protected up front so a vanished root never purges its index.
  absentRootPaths: string[]
  // path → modified_at (ms) of the current index. Keys drive the retention diff.
  existing: Map<string, number>
  fs: ScanFs
  // Path separator used to test prefix containment (Windows: '\\').
  sep: string
}

// Compute the incremental scan plan: walk the roots, collect every path seen,
// track which directories failed to enumerate, and diff against the existing
// index. NEVER produces a blind clear — a path is only in `toDelete` when it was
// previously indexed, not seen this scan, and not under a failed/absent prefix.
// Mirrors macOS FileIndexerService.scanFolders (failedDirectories + pathsToDelete).
export async function planScan(opts: PlanScanOptions): Promise<ScanPlan> {
  const { roots, absentRootPaths, existing, fs, sep } = opts

  const scannedPaths = new Set<string>()
  const toUpsert: IndexedFileRecord[] = []
  // Seed with absent candidate roots so a vanished/unmounted root protects its subtree.
  const failedPrefixes = new Set<string>(absentRootPaths)

  // Record a file: mark it seen, then queue it for upsert.
  const recordFile = (rec: IndexedFileRecord): void => {
    scannedPaths.add(rec.path)
    toUpsert.push(rec)
  }

  // Enumerate a directory; on failure protect its subtree and continue (fail-open).
  const readDirSafe = async (dir: string): Promise<ScanDirEntry[]> => {
    try {
      return await fs.readDir(dir)
    } catch {
      // Enumeration failure is a READ error, not deletion — protect this subtree.
      failedPrefixes.add(dir)
      return []
    }
  }

  const walkFiles = async (root: string): Promise<void> => {
    const recurse = async (dir: string, depth: number): Promise<void> => {
      for (const ent of await readDirSafe(dir)) {
        if (isHiddenEntry(ent.name)) continue
        const full = join(dir, ent.name)
        if (ent.isDirectory) {
          if (shouldVisitDir(ent.name, depth + 1)) await recurse(full, depth + 1)
        } else if (ent.isFile) {
          let st: ScanStat
          try {
            st = await fs.stat(full)
          } catch {
            continue // per-file read failure — skip this one file, keep walking
          }
          if (!shouldIndexFile(st.size)) continue
          recordFile({
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
        }
      }
    }
    await recurse(root, 0)
  }

  const walkApps = async (root: string): Promise<void> => {
    const recurse = async (dir: string, depth: number): Promise<void> => {
      if (depth > MAX_DEPTH) return
      for (const ent of await readDirSafe(dir)) {
        if (isHiddenEntry(ent.name)) continue
        const full = join(dir, ent.name)
        if (ent.isDirectory) {
          await recurse(full, depth + 1)
        } else if (ent.isFile && ent.name.toLowerCase().endsWith('.lnk')) {
          let st: ScanStat
          try {
            st = await fs.stat(full)
          } catch {
            continue
          }
          recordFile({
            path: full,
            filename: basename(ent.name, '.lnk'),
            extension: 'lnk',
            fileType: 'application',
            sizeBytes: st.size,
            folder: dir,
            depth,
            createdAt: Math.round(st.birthtimeMs),
            modifiedAt: Math.round(st.mtimeMs),
            targetPath: fs.resolveShortcutTarget(full)
          })
        }
      }
    }
    await recurse(root, 0)
  }

  for (const r of roots) {
    if (r.kind === 'apps') await walkApps(r.path)
    else await walkFiles(r.path)
  }

  const toDelete = pathsToDelete(scannedPaths, new Set(existing.keys()), failedPrefixes, sep)
  return { toUpsert, toDelete: [...toDelete], failedPrefixes: [...failedPrefixes] }
}
