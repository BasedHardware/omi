import { join } from 'path'
import { homedir } from 'os'
import type { ModelEntry } from '../../shared/types'

/**
 * Hugging Face cache dedupe + resume helpers. Pure string/number math so the
 * tricky parts are unit-testable without touching disk or the network.
 *
 * HF hub cache layout (under a cache root, default ~/.cache/huggingface/hub):
 *   models--<org>--<name>/
 *     refs/<revision>          -> file containing the snapshot commit sha
 *     snapshots/<commit>/<file> -> (usually) a symlink into ../../blobs/<oid>
 *     blobs/<oid>              -> the real bytes; oid == sha256 for LFS files
 * So if we know the expected sha256 we can look up blobs/<sha256> directly; if
 * not we resolve refs/<revision> -> snapshots/<commit>/<file> and follow it.
 */

// HF repo-id sanitization for the cache dir name (per huggingface_hub rules).
export function repoCacheDirName(repo: string): string {
  const [ns, name] = repo.includes('/') ? repo.split('/') : ['', repo]
  const slug = (ns ? `${ns}--${name}` : name).replace(/[^a-zA-Z0-9._-]/g, ':')
  return `models--${slug}`
}

export function defaultCacheRoots(env: NodeJS.ProcessEnv = process.env, home = homedir()): string[] {
  const roots: string[] = []
  if (env.HF_HUB_CACHE) roots.push(env.HF_HUB_CACHE)
  if (env.HF_HOME) roots.push(join(env.HF_HOME, 'hub'))
  roots.push(join(home, '.cache', 'huggingface', 'hub'))
  // de-dupe, preserve order
  return [...new Set(roots)]
}

/** Candidate cache file paths to check for an existing copy of `entry`. */
export function cacheCandidates(
  cacheRoot: string,
  entry: ModelEntry,
  commitForRevision?: string
): string[] {
  const repoDir = join(cacheRoot, repoCacheDirName(entry.repo))
  const out: string[] = []
  // Strongest: content-addressed blob when we know the sha256.
  if (entry.sha256) out.push(join(repoDir, 'blobs', entry.sha256))
  // Otherwise the snapshot checkout for the resolved commit (symlink to blob).
  const commit = commitForRevision
  if (commit) out.push(join(repoDir, 'snapshots', commit, entry.file))
  // The ref itself, so the caller can resolve revision -> commit.
  return out
}

export function refPath(cacheRoot: string, entry: ModelEntry): string {
  return join(cacheRoot, repoCacheDirName(entry.repo), 'refs', entry.revision)
}

export interface ResumePlan {
  /** HTTP Range header to send, or undefined to start from scratch. */
  rangeHeader?: string
  /** byte offset at which we resume (== current .part size). */
  start: number
  /** true when the part file already equals the full size -> just verify. */
  complete: boolean
}

/**
 * Decide how to (re)start a download given bytes already on disk. A part file of
 * size `existing` resumes at `existing`; an unexpected/exact size short-circuits.
 */
export function planResume(existing: number, total: number): ResumePlan {
  if (existing <= 0) return { start: 0, complete: false, rangeHeader: undefined }
  if (total > 0 && existing >= total) return { start: existing, complete: true }
  return { start: existing, complete: false, rangeHeader: `bytes=${existing}-` }
}
