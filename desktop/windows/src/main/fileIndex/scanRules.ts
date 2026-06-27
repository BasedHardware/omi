export const MAX_DEPTH = 3
export const MAX_FILE_SIZE = 500 * 1024 * 1024 // 500 MB, matching macOS
export const SKIP_DIRS = new Set(['.Trash', 'node_modules', '.git', '__pycache__'])

// True when a subdirectory at `depth` should be descended into.
export function shouldVisitDir(name: string, depth: number): boolean {
  return depth <= MAX_DEPTH && !SKIP_DIRS.has(name)
}

// True when a file of `sizeBytes` should be recorded.
export function shouldIndexFile(sizeBytes: number): boolean {
  return sizeBytes >= 0 && sizeBytes <= MAX_FILE_SIZE
}
