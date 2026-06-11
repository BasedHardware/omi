import { join } from 'path'

export type ScanRoot = { path: string; kind: 'files' | 'apps' }

export type ScanEnv = {
  USERPROFILE?: string
  ProgramData?: string
  APPDATA?: string
}

const DOC_DIRS = ['Downloads', 'Documents', 'Desktop']
const DEV_DIRS = ['Developer', 'Projects', 'Code', 'src', 'repos', 'Sites']
const START_MENU = join('Microsoft', 'Windows', 'Start Menu', 'Programs')

// Resolve the Windows scan roots, keeping only paths that exist. Doc + dev
// folders are 'files'; the Start-Menu shortcut folders are the Windows analog
// of macOS /Applications and are tagged 'apps' (enumerated as .lnk installs).
export function resolveScanRoots(env: ScanEnv, exists: (p: string) => boolean): ScanRoot[] {
  const roots: ScanRoot[] = []
  const home = env.USERPROFILE
  if (home) {
    for (const d of DOC_DIRS) {
      const p = join(home, d)
      if (exists(p)) roots.push({ path: p, kind: 'files' })
    }
    const repos = join(home, 'source', 'repos') // Visual Studio default
    if (exists(repos)) roots.push({ path: repos, kind: 'files' })
    for (const d of DEV_DIRS) {
      const p = join(home, d)
      if (exists(p)) roots.push({ path: p, kind: 'files' })
    }
  }
  for (const base of [env.ProgramData, env.APPDATA]) {
    if (!base) continue
    const p = join(base, START_MENU)
    if (exists(p)) roots.push({ path: p, kind: 'apps' })
  }
  return roots
}
