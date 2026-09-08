// Windows port of desktop/macos/agent/src/runtime/artifact-filters.ts.

/** Basenames skipped when scanning managed run artifact directories. */
const MANAGED_RUN_ARTIFACT_DENYLIST = new Set([
  '.claude',
  '.codex',
  '.cursor',
  '.DS_Store',
  '.git',
  '.pytest_cache',
  '.venv',
  '__pycache__',
  'node_modules',
  'venv'
])

export function isDeniedManagedRunArtifactBasename(name: string): boolean {
  return MANAGED_RUN_ARTIFACT_DENYLIST.has(name)
}
