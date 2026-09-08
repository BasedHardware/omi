export const MAX_DEPTH = 3
export const MAX_FILE_SIZE = 500 * 1024 * 1024 // 500 MB, matching macOS

// Noise directories whose whole subtree is skipped. Ported from macOS
// FileIndexScanPolicy.swift (the `skipFolders` set) plus a handful of Windows /
// .NET analogs macOS has no reason to know about. Dot-prefixed entries
// (.git, .venv, .cache, …) are ALSO caught by isHiddenEntry, but they are kept
// here to mirror the Mac list 1:1 and to document intent.
export const SKIP_DIRS = new Set<string>([
  // --- macOS FileIndexScanPolicy.skipFolders ---
  '.Trash',
  'node_modules',
  '.git',
  '__pycache__',
  '.venv',
  'venv',
  '.cache',
  '.npm',
  '.yarn',
  'Pods',
  'DerivedData',
  '.build',
  'build',
  'dist',
  '.next',
  '.nuxt',
  'target',
  'vendor',
  'Library',
  '.local',
  '.cargo',
  '.rustup',
  // --- Windows / .NET / Visual Studio build + cache analogs ---
  'obj', // MSBuild intermediate output (paired with %USERPROFILE%\source\repos)
  'bin', // .NET compiled output
  'packages', // NuGet packages restore dir
  '.gradle', // (also dot-hidden) Gradle cache
  '.terraform', // (also dot-hidden) Terraform provider cache
  '$RECYCLE.BIN', // per-volume recycle bin
  'OneDriveTemp' // OneDrive scratch dir
])
const NORMALIZED_SKIP_DIRS = new Set([...SKIP_DIRS].map((name) => name.toLowerCase()))

// True for dot-prefixed entries (dotfiles and dot-directories). Mirrors macOS's
// `.skipsHiddenFiles` enumeration option, which the Node `fs.readdir` walk has no
// equivalent for (Dirent carries no hidden/system attribute). Applied to BOTH
// files and directories so hidden config trees (.vscode, .idea, .DS_Store, …) and
// dotfiles are excluded uniformly.
export function isHiddenEntry(name: string): boolean {
  return name.startsWith('.')
}

// True when a subdirectory at `depth` should be descended into.
export function shouldVisitDir(name: string, depth: number): boolean {
  return depth <= MAX_DEPTH && !isHiddenEntry(name) && !NORMALIZED_SKIP_DIRS.has(name.toLowerCase())
}

// True when a file of `sizeBytes` should be recorded. 0-byte files are indexed
// (metadata-only index; an empty file is still a real path worth surfacing).
export function shouldIndexFile(sizeBytes: number): boolean {
  return sizeBytes >= 0 && sizeBytes <= MAX_FILE_SIZE
}

// Pure retention diff, ported 1:1 from macOS FileIndexerService.pathsToDelete
// (FileIndexerService.swift:380-390). A previously-indexed path is deleted ONLY
// when it was NOT seen this scan AND is NOT under a directory/root whose
// enumeration failed or was absent (`protectedPrefixes`). This is what turns a
// transient unreadable folder (permission blip, AV lock, unmounted drive) into a
// no-op instead of a data-loss event: without the protected-prefix guard a single
// unreadable root would purge its entire indexed subtree.
//
// `sep` is the path separator that joins a prefix to its children (Windows: '\\').
// A path is protected when it equals a prefix or starts with `prefix + sep`.
export function pathsToDelete(
  scannedPaths: Set<string>,
  existingPaths: Set<string>,
  protectedPrefixes: Set<string>,
  sep: string
): Set<string> {
  const out = new Set<string>()
  for (const path of existingPaths) {
    if (scannedPaths.has(path)) continue
    let isProtected = false
    for (const prefix of protectedPrefixes) {
      if (path === prefix || path.startsWith(prefix + sep)) {
        isProtected = true
        break
      }
    }
    if (!isProtected) out.add(path)
  }
  return out
}
