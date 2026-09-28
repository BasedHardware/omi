/**
 * Backend-process provenance stamp.
 *
 * TypeScript twin of `worktreeStamp()` in the sibling repo's
 * `core-foundation/integration/lib/provenance.mjs` — read that file for the
 * full rationale. It cannot be imported directly (it is a node ESM module in
 * a different repo, and this process runs under Bun), so this reimplements
 * the SAME ALGORITHM against the SAME shape:
 *
 *   treeHash = the git tree object id of HEAD with the working-tree state of
 *   the declared source roots overlaid, computed via a THROWAWAY index file
 *   (`GIT_INDEX_FILE`) so the repo's real index is never touched.
 *
 * Computed ONCE at module load, not per request — see `serve.ts`, which reads
 * `BACKEND_PROCESS_STAMP` (already-computed) into the `/qa/stats` body rather
 * than calling into git on every request.
 *
 * If git is unavailable or any step fails, the result is `{ ..., unavailable:
 * "<reason>" }` — deliberately shaped so it can never be confused with a real
 * stamp (no `treeHash` field at all, rather than a placeholder value).
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** Bumped when the stamp shape changes in a way a consumer must notice. Mirrors PROVENANCE_SCHEMA_VERSION in the .mjs module. */
export const PROVENANCE_SCHEMA_VERSION = 1 as const;

const REPO = "platform" as const;
const ARTIFACT = "backend-process" as const;

/**
 * Copied by hand from `REPO_SOURCE_ROOTS.platform` in
 * core-foundation/integration/lib/provenance.mjs. Keep the two lists in sync;
 * this is a small, declared, rarely-changing list, not something worth an
 * inter-repo import for.
 */
const SOURCE_ROOTS: readonly string[] = [
  "apps",
  "core",
  "drivers",
  "harness",
  "integration",
  "contract-tests",
  "scripts",
  "vendor",
  "contracts.lock.json",
  "package.json",
];

const HERE = dirname(fileURLToPath(import.meta.url));
/** `<platform>/integration/server` -> `<platform>` */
const REPO_ROOT = join(HERE, "..", "..");

export interface BackendProcessStamp {
  readonly schema: typeof PROVENANCE_SCHEMA_VERSION;
  readonly repo: typeof REPO;
  readonly artifact: typeof ARTIFACT;
  readonly branch: string;
  readonly commit: string;
  readonly treeHash: string;
  readonly dirty: boolean;
  readonly roots: readonly string[];
  readonly stampedAt: string;
}

export interface UnavailableBackendStamp {
  readonly schema: typeof PROVENANCE_SCHEMA_VERSION;
  readonly repo: typeof REPO;
  readonly artifact: typeof ARTIFACT;
  readonly unavailable: string;
}

export type BackendStamp = BackendProcessStamp | UnavailableBackendStamp;

function git(args: readonly string[], cwd: string, env: Record<string, string> = {}): string {
  return execFileSync("git", args as string[], {
    cwd,
    encoding: "utf8",
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

/**
 * The tree id of HEAD with the working state of `roots` overlaid, via a
 * throwaway index seeded from HEAD. Never touches the repo's real index.
 */
function overlayTreeHash(
  repoRoot: string,
  roots: readonly string[],
): { readonly treeHash: string; readonly roots: readonly string[] } {
  const scratch = mkdtempSync(join(tmpdir(), "omi-provenance-"));
  const indexFile = join(scratch, "index");
  try {
    git(["read-tree", "HEAD"], repoRoot, { GIT_INDEX_FILE: indexFile });
    const present = roots.filter((root) => existsSync(join(repoRoot, root)));
    if (present.length > 0) {
      git(["add", "-A", "--", ...present], repoRoot, { GIT_INDEX_FILE: indexFile });
    }
    return {
      treeHash: git(["write-tree"], repoRoot, { GIT_INDEX_FILE: indexFile }),
      roots: present,
    };
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

function computeStamp(now: Date): BackendStamp {
  try {
    const { treeHash, roots } = overlayTreeHash(REPO_ROOT, SOURCE_ROOTS);
    const commit = git(["rev-parse", "HEAD"], REPO_ROOT);
    const commitTree = git(["rev-parse", "HEAD^{tree}"], REPO_ROOT);
    let branch: string;
    try {
      branch = git(["rev-parse", "--abbrev-ref", "HEAD"], REPO_ROOT);
    } catch {
      branch = "(detached)";
    }
    return {
      schema: PROVENANCE_SCHEMA_VERSION,
      repo: REPO,
      artifact: ARTIFACT,
      branch,
      commit,
      treeHash,
      dirty: treeHash !== commitTree,
      roots,
      stampedAt: now.toISOString(),
    };
  } catch (caught) {
    return {
      schema: PROVENANCE_SCHEMA_VERSION,
      repo: REPO,
      artifact: ARTIFACT,
      unavailable: caught instanceof Error ? caught.message : String(caught),
    };
  }
}

/**
 * The provenance stamp of this backend process's source tree, computed once
 * when this module first loads. Import and read this constant — do not call
 * anything in this file per request; the whole point of computing it at load
 * is that `/qa/stats` pays zero git cost per request.
 */
export const BACKEND_PROCESS_STAMP: BackendStamp = computeStamp(new Date());
