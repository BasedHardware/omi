import { join } from 'path'

export type StickyNotesEnv = { LOCALAPPDATA?: string }

const PACKAGE_PREFIX = 'Microsoft.MicrosoftStickyNotes_'

// Pure: resolve the Sticky Notes plum.sqlite path. The UWP package dir carries a
// publisher-id suffix that varies per install, so we list %LOCALAPPDATA%\Packages
// and match the prefix. `listDirs` is expected to return entries newest-first;
// the first match whose plum.sqlite exists wins. Returns null when Sticky Notes
// isn't installed or has no database yet.
export function resolveStickyNotesDb(
  env: StickyNotesEnv,
  listDirs: (packagesDir: string) => string[],
  exists: (p: string) => boolean
): string | null {
  const local = env.LOCALAPPDATA
  if (!local) return null
  const packages = join(local, 'Packages')
  for (const name of listDirs(packages)) {
    if (!name.startsWith(PACKAGE_PREFIX)) continue
    const candidate = join(packages, name, 'LocalState', 'plum.sqlite')
    if (exists(candidate)) return candidate
  }
  return null
}
