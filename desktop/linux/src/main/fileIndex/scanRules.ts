export const MAX_DEPTH = 3
export const MAX_FILE_SIZE = 500 * 1024 * 1024 // 500 MB, matching macOS
// Keep this aligned with FileIndexScanPolicy.standard on macOS.
export const SKIP_DIRS = new Set([
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
  '.rustup'
])
const NORMALIZED_SKIP_DIRS = new Set([...SKIP_DIRS].map((name) => name.toLowerCase()))

// True when a subdirectory at `depth` should be descended into.
export function shouldVisitDir(name: string, depth: number): boolean {
  return depth <= MAX_DEPTH && !NORMALIZED_SKIP_DIRS.has(name.toLowerCase())
}

// True when a file of `sizeBytes` should be recorded.
export function shouldIndexFile(sizeBytes: number): boolean {
  return sizeBytes >= 0 && sizeBytes <= MAX_FILE_SIZE
}
