import { app, ipcMain } from 'electron'
import { lstat, readdir, realpath } from 'fs/promises'
import { join, extname, sep } from 'path'
import { setImmediate as yieldToMainLoop } from 'timers/promises'
import { apiRequest } from './apiProxy'
import { getAuthState } from './auth'

// Lightweight file indexing (FileIndexerService.swift): scans a few well-known
// folders, builds a summary of the user's projects/files, and seeds it as a
// memory so Omi has context about what they work on. Best-effort, on demand.

const SCAN_DIRS = ['Downloads', 'Documents', 'Desktop']
const SKIP = new Set(['node_modules', '.git', '__pycache__', '.venv', '.build', 'AppData'])
const MAX_DEPTH = 2
const MAX_ENTRIES = 4000

interface Scan {
  files: number
  byExt: Map<string, number>
  topFolders: string[]
}

async function scanDir(base: string, root: string, depth: number, acc: Scan): Promise<void> {
  if (depth > MAX_DEPTH || acc.files >= MAX_ENTRIES) return
  let entries: string[]
  try {
    entries = await readdir(root)
  } catch {
    return
  }
  for (const name of entries) {
    if (acc.files >= MAX_ENTRIES) break
    if (name.startsWith('.') || SKIP.has(name)) continue
    const full = join(root, name)
    let st
    try {
      st = await lstat(full)
    } catch {
      continue
    }
    if (st.isSymbolicLink()) continue // never follow symlinks
    if (st.isDirectory()) {
      // Confine traversal: skip junctions/links that resolve outside the scan root.
      let real: string
      try {
        real = await realpath(full)
      } catch {
        continue
      }
      if (real !== base && !real.startsWith(base + sep)) continue
      if (depth === 0) acc.topFolders.push(name)
      await scanDir(base, full, depth + 1, acc)
    } else {
      acc.files++
      const ext = extname(name).toLowerCase() || '(none)'
      acc.byExt.set(ext, (acc.byExt.get(ext) ?? 0) + 1)
      if (acc.files % 100 === 0) await yieldToMainLoop()
    }
  }
}

export async function indexFiles(): Promise<{ ok: boolean; summary?: string; error?: string }> {
  if (!getAuthState().signedIn) return { ok: false, error: 'not signed in' }
  const acc: Scan = { files: 0, byExt: new Map(), topFolders: [] }
  for (const dir of SCAN_DIRS) {
    try {
      const rootPath = await realpath(app.getPath(dir.toLowerCase() as 'downloads' | 'documents' | 'desktop'))
      await scanDir(rootPath, rootPath, 0, acc)
    } catch {
      // folder may not exist
    }
  }
  const topExts = [...acc.byExt.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([ext, n]) => `${ext} (${n})`)
    .join(', ')
  const folders = acc.topFolders.slice(0, 20).join(', ')
  const summary =
    `User's computer has ~${acc.files} files across Downloads/Documents/Desktop. ` +
    `Most common file types: ${topExts}. Top folders: ${folders}.`

  try {
    const res = await apiRequest({
      method: 'POST',
      url: 'v3/memories',
      base: 'python',
      body: JSON.stringify({ content: summary, visibility: 'private', source: 'desktop', category: 'system' })
    })
    if (res.status >= 200 && res.status < 300) return { ok: true, summary }
    return { ok: false, error: `HTTP ${res.status}` }
  } catch (e) {
    return { ok: false, error: String(e) }
  }
}

export function registerFileIndexIpc(): void {
  ipcMain.handle('files:index', () => indexFiles())
}
