import { describe, it, expect } from 'vitest'
import { join, sep } from 'path'
import { planScan, type ScanFs, type ScanDirEntry, type ScanStat } from './scanPlan'
import type { ScanRoot } from './scanRoots'

// --- In-memory ScanFs fake ---------------------------------------------------
const FILE = (name: string): ScanDirEntry => ({ name, isDirectory: false, isFile: true })
const DIR = (name: string): ScanDirEntry => ({ name, isDirectory: true, isFile: false })
const stat = (size = 10, mtimeMs = 1000): ScanStat => ({ size, birthtimeMs: 500, mtimeMs })

function makeFs(opts: {
  dirs: Record<string, ScanDirEntry[]>
  stats?: Record<string, ScanStat>
  failing?: string[]
  shortcuts?: Record<string, string | undefined>
}): ScanFs {
  const failing = new Set(opts.failing ?? [])
  const stats = opts.stats ?? {}
  return {
    async readDir(dir) {
      if (failing.has(dir)) throw new Error(`EACCES: simulated enumeration failure at ${dir}`)
      return opts.dirs[dir] ?? []
    },
    async stat(path) {
      const s = stats[path]
      if (!s) throw new Error(`ENOENT: ${path}`)
      return s
    },
    resolveShortcutTarget: (lnk) => opts.shortcuts?.[lnk]
  }
}

const filesRoot = (path: string): ScanRoot => ({ path, kind: 'files' })

describe('planScan — data-loss retention guard', () => {
  it('does NOT purge a root whose enumeration fails mid-walk, but DOES prune a genuinely-deleted file under a healthy root', async () => {
    const downloads = join('C:\\U', 'Downloads')
    const documents = join('C:\\U', 'Documents')
    const keep = join(downloads, 'keep.txt')
    const removed = join(downloads, 'removed.txt')
    const important = join(documents, 'important.txt')

    const fs = makeFs({
      dirs: { [downloads]: [FILE('keep.txt')] }, // removed.txt is gone from disk
      stats: { [keep]: stat(10, 2000) }, // mtime moved since last scan → upsert
      failing: [documents] // Documents throws on enumeration this run
    })

    // Everything was indexed on a previous, successful scan.
    const existing = new Map<string, number>([
      [keep, 1000],
      [removed, 1000],
      [important, 1000]
    ])

    const plan = await planScan({
      roots: [filesRoot(downloads), filesRoot(documents)],
      absentRootPaths: [],
      existing,
      fs,
      sep
    })

    // The transiently-unreadable root is recorded as protected...
    expect(plan.failedPrefixes).toContain(documents)
    // ...so its previously-indexed rows SURVIVE (never scheduled for deletion).
    expect(plan.toDelete).not.toContain(important)
    // A genuinely-deleted file under the HEALTHY root IS pruned.
    expect(plan.toDelete).toContain(removed)
    // The still-present file is re-recorded.
    expect(plan.toUpsert.map((r) => r.path)).toContain(keep)
  })

  it('protects the subtree of an absent candidate root (unmounted drive)', async () => {
    const gone = 'D:\\repos'
    const gonePath = join(gone, 'project', 'main.rs')
    const existing = new Map<string, number>([[gonePath, 1000]])

    const plan = await planScan({
      roots: [], // resolveScanRoots dropped the absent root — it is not walked
      absentRootPaths: [gone],
      existing,
      fs: makeFs({ dirs: {} }),
      sep
    })

    expect(plan.toDelete).not.toContain(gonePath) // must not vanish while drive is offline
    expect(plan.failedPrefixes).toContain(gone)
  })

  it('never produces a blind clear: a fully-unreadable index deletes nothing', async () => {
    const root = 'C:\\U\\Documents'
    const existing = new Map<string, number>([
      [join(root, 'a.txt'), 1],
      [join(root, 'b.txt'), 2]
    ])
    const plan = await planScan({
      roots: [filesRoot(root)],
      absentRootPaths: [],
      existing,
      fs: makeFs({ dirs: {}, failing: [root] }),
      sep
    })
    expect(plan.toDelete).toEqual([])
    expect(plan.toUpsert).toEqual([])
  })
})

describe('planScan — walk behavior', () => {
  const root = 'C:\\U\\Downloads'

  it('records file metadata and skips the skip-list + hidden subtrees', async () => {
    const good = join(root, 'notes.md')
    const nmFile = join(root, 'node_modules', 'left-pad', 'index.js')
    const dotFile = join(root, '.env')
    const gitFile = join(root, '.git', 'config')

    const fs = makeFs({
      dirs: {
        [root]: [FILE('notes.md'), FILE('.env'), DIR('node_modules'), DIR('.git')]
        // node_modules and .git are never enumerated because they are skipped.
      },
      stats: { [good]: stat(42, 7000) }
    })

    const plan = await planScan({
      roots: [filesRoot(root)],
      absentRootPaths: [],
      existing: new Map(),
      fs,
      sep
    })
    const paths = plan.toUpsert.map((r) => r.path)

    expect(paths).toContain(good)
    expect(paths).not.toContain(nmFile)
    expect(paths).not.toContain(dotFile)
    expect(paths).not.toContain(gitFile)

    const rec = plan.toUpsert.find((r) => r.path === good)!
    expect(rec).toMatchObject({
      filename: 'notes.md',
      extension: 'md',
      fileType: 'document',
      sizeBytes: 42,
      folder: root,
      depth: 0,
      modifiedAt: 7000
    })
  })

  it('respects the max-depth cap', async () => {
    // depth 0 root → d1 → d2 → d3 (indexable) → d4 (NOT descended past MAX_DEPTH=3)
    const d1 = join(root, 'a')
    const d2 = join(d1, 'b')
    const d3 = join(d2, 'c')
    const d4 = join(d3, 'd')
    const deepFile = join(d3, 'ok.txt')
    const tooDeep = join(d4, 'nope.txt')

    const fs = makeFs({
      dirs: {
        [root]: [DIR('a')],
        [d1]: [DIR('b')],
        [d2]: [DIR('c')],
        [d3]: [FILE('ok.txt'), DIR('d')],
        [d4]: [FILE('nope.txt')]
      },
      stats: { [deepFile]: stat(), [tooDeep]: stat() }
    })

    const plan = await planScan({
      roots: [filesRoot(root)],
      absentRootPaths: [],
      existing: new Map(),
      fs,
      sep
    })
    const paths = plan.toUpsert.map((r) => r.path)
    expect(paths).toContain(deepFile)
    expect(paths).not.toContain(tooDeep)
  })

  it('skips a single unreadable file without aborting the walk', async () => {
    const ok = join(root, 'ok.txt')
    // locked.bin's stat throws (no stats entry) → it is skipped, walk continues.
    const fs = makeFs({
      dirs: { [root]: [FILE('ok.txt'), FILE('locked.bin')] },
      stats: { [ok]: stat() }
    })
    const plan = await planScan({
      roots: [filesRoot(root)],
      absentRootPaths: [],
      existing: new Map(),
      fs,
      sep
    })
    expect(plan.toUpsert.map((r) => r.path)).toEqual([ok])
  })

  it('incrementally skips unchanged files but upserts new + mtime-changed ones', async () => {
    const unchanged = join(root, 'unchanged.txt')
    const changed = join(root, 'changed.txt')
    const fresh = join(root, 'fresh.txt')

    const fs = makeFs({
      dirs: { [root]: [FILE('unchanged.txt'), FILE('changed.txt'), FILE('fresh.txt')] },
      stats: {
        [unchanged]: stat(10, 1000), // same mtime as existing → skip upsert
        [changed]: stat(10, 2000), // mtime moved → upsert
        [fresh]: stat(10, 3000) // brand new → upsert
      }
    })
    const existing = new Map<string, number>([
      [unchanged, 1000],
      [changed, 1500] // old mtime
    ])

    const plan = await planScan({
      roots: [filesRoot(root)],
      absentRootPaths: [],
      existing,
      fs,
      sep
    })
    const upserted = plan.toUpsert.map((r) => r.path).sort()

    expect(upserted).toEqual([changed, fresh].sort())
    expect(upserted).not.toContain(unchanged)
    // The unchanged file is still "seen", so it is NOT pruned by the retention diff.
    expect(plan.toDelete).not.toContain(unchanged)
  })

  it('indexes Start-Menu .lnk shortcuts as apps with resolved targets', async () => {
    const appsRoot = 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs'
    const lnk = join(appsRoot, 'Slack.lnk')
    const notLnk = join(appsRoot, 'readme.txt')
    const fs = makeFs({
      dirs: { [appsRoot]: [FILE('Slack.lnk'), FILE('readme.txt')] },
      stats: { [lnk]: stat(1, 2000), [notLnk]: stat() },
      shortcuts: { [lnk]: 'C:\\Apps\\slack.exe' }
    })
    const plan = await planScan({
      roots: [{ path: appsRoot, kind: 'apps' }],
      absentRootPaths: [],
      existing: new Map(),
      fs,
      sep
    })
    expect(plan.toUpsert).toHaveLength(1)
    expect(plan.toUpsert[0]).toMatchObject({
      filename: 'Slack',
      extension: 'lnk',
      fileType: 'application',
      targetPath: 'C:\\Apps\\slack.exe'
    })
  })
})
