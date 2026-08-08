// LIFECYCLE: permanent
//
// Build provenance — the one thing that would have caught most of the night's
// false greens on its own.
//
// Every false-green in this program's history shares one shape: **the artifact
// measured was not the artifact edited.** A stale `dist` tested yesterday's
// client. A shell launched from a build dir someone else had rebuilt. A backend
// running the branch you switched away from. In each case every individual
// measurement was accurate and the conclusion was wrong, because two of the
// measurements were about different artifacts and nothing joined them.
//
// So every built artifact carries a stamp of the source it was built from, and
// `--assert` requires all the stamps to agree with the working tree. That single
// cross-check subsumes "stale dist", "wrong shell", "wrong branch" and
// "edited-but-not-rebuilt" — you do not need a separate check for each.
//
// WHAT `treeHash` IS, precisely
// ----------------------------
// The git tree object id of: HEAD, with the working-tree state of the declared
// source roots overlaid. Not `git rev-parse HEAD` (which ignores every
// uncommitted edit — the common case while iterating) and not a hash of
// `git status` output (which is a hash of a *description* of the tree, and
// changes shape between git versions).
//
// It is a real content-addressed tree id, so two checkouts with identical source
// produce an identical hash, and any edit to a declared root changes it. That is
// what makes it usable as a receipt key.
//
// WHY THE ROOTS ARE SCOPED. `git add -A` over the whole monorepo costs ~1.3s
// because it enumerates every untracked path under a large tree; scoped to the
// roots that can change behavior it costs ~0.06s. At L0's <1s budget the
// difference decides whether provenance is computed every run or skipped. The
// roots are declared here, in one place, and travel inside the stamp itself so a
// stamp is self-describing rather than depending on the reader agreeing about
// scope.
//
// Ignored paths (`dist/`, `.build/`, `node_modules/`) are excluded by gitignore,
// which is exactly right: building must not change the tree hash, or every
// receipt would be invalidated by the build that produced its evidence.

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

/** Bumped when the stamp shape changes in a way a consumer must notice. */
export const PROVENANCE_SCHEMA_VERSION = 1;

/**
 * Source roots per repository: the directories whose content can change what an
 * artifact does. Declared, not inferred — an inferred root list silently grows
 * to include build output and then no two runs ever agree.
 */
export const REPO_SOURCE_ROOTS = Object.freeze({
  "core-foundation": Object.freeze(["core", "integration"]),
  platform: Object.freeze([
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
  ]),
});

/**
 * Per-artifact root scoping. An artifact's stamp must go stale when the source
 * that BUILT it changes, and must NOT go stale when unrelated source changes.
 *
 * Without this, editing `integration/dev-stack.sh` invalidated the surfaces
 * `dist` stamp and `--assert` demanded a full rebuild of a bundle whose inputs
 * had not moved. That is the failure mode of every over-broad staleness check:
 * it is technically conservative, it is wrong often enough to be ignored, and an
 * ignored check is worse than no check. The surfaces bundle and the macOS app
 * are built from `core/` only; the launcher is not an input to either.
 *
 * A stamp carries its own `roots`, so the comparator recomputes the working-tree
 * hash using THE ARTIFACT'S scope (`worktreeStampMatching`) rather than assuming
 * both sides agreed about it.
 */
export const ARTIFACT_SOURCE_ROOTS = Object.freeze({
  "surfaces-dist": Object.freeze(["core"]),
  "macos-app": Object.freeze(["core"]),
  "ios-bundle": Object.freeze(["core"]),
});

const HERE = dirname(fileURLToPath(import.meta.url));
/** `<workspace>/core-foundation/integration/lib` -> `<workspace>` */
export const WORKSPACE_ROOT = join(HERE, "..", "..", "..");
export const REPO_PATHS = Object.freeze({
  "core-foundation": join(WORKSPACE_ROOT, "core-foundation"),
  platform: join(WORKSPACE_ROOT, "platform"),
});

function git(args, { cwd, env = {} }) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

/**
 * The tree id of HEAD with the working state of `roots` overlaid.
 *
 * Uses a THROWAWAY index (`GIT_INDEX_FILE`) seeded from HEAD. It never touches
 * the repository's real index, so running this while someone has files staged
 * cannot disturb their staging area — a harness that mutates the user's index to
 * measure it would be its own kind of false evidence.
 */
function overlayTreeHash(repoRoot, roots) {
  const scratch = mkdtempSync(join(tmpdir(), "omi-provenance-"));
  const indexFile = join(scratch, "index");
  try {
    git(["read-tree", "HEAD"], { cwd: repoRoot, env: { GIT_INDEX_FILE: indexFile } });
    const present = roots.filter((root) => existsSync(join(repoRoot, root)));
    if (present.length > 0) {
      git(["add", "-A", "--", ...present], { cwd: repoRoot, env: { GIT_INDEX_FILE: indexFile } });
    }
    return {
      treeHash: git(["write-tree"], { cwd: repoRoot, env: { GIT_INDEX_FILE: indexFile } }),
      roots: present,
    };
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

/**
 * Stamp the CURRENT WORKING TREE of a repo.
 *
 * `artifact` names what is being stamped ("surfaces-dist", "macos-app",
 * "backend-process", "worktree"). A stamp without it is still valid; the field
 * exists so a mismatch report can say WHICH artifact is stale instead of just
 * that something is.
 */
export function worktreeStamp({ repo, repoRoot, artifact = "worktree", roots: rootsOverride, now = new Date() } = {}) {
  const resolvedRepo = repo ?? "core-foundation";
  const resolvedRoot = repoRoot ?? REPO_PATHS[resolvedRepo];
  const roots = rootsOverride ?? ARTIFACT_SOURCE_ROOTS[artifact] ?? REPO_SOURCE_ROOTS[resolvedRepo] ?? ["."];
  const { treeHash, roots: presentRoots } = overlayTreeHash(resolvedRoot, roots);
  const commit = git(["rev-parse", "HEAD"], { cwd: resolvedRoot });
  const commitTree = git(["rev-parse", "HEAD^{tree}"], { cwd: resolvedRoot });
  let branch = "";
  try {
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], { cwd: resolvedRoot });
  } catch {
    branch = "(detached)";
  }
  return {
    schema: PROVENANCE_SCHEMA_VERSION,
    repo: resolvedRepo,
    artifact,
    branch,
    commit,
    treeHash,
    dirty: treeHash !== commitTree,
    roots: presentRoots,
    stampedAt: now.toISOString(),
  };
}

/** Stamps for every repo in the workspace, keyed by repo name. */
export function workspaceStamps({ artifact = "worktree" } = {}) {
  const out = {};
  for (const [repo, repoRoot] of Object.entries(REPO_PATHS)) {
    if (!existsSync(join(repoRoot, ".git"))) continue;
    out[repo] = worktreeStamp({ repo, repoRoot, artifact });
  }
  return out;
}

export function writeStampFile(path, stamp) {
  writeFileSync(path, `${JSON.stringify(stamp, null, 2)}\n`);
  return stamp;
}

/** Returns null rather than throwing: an absent stamp is a normal finding. */
export function readStampFile(path) {
  try {
    const parsed = JSON.parse(readFileSync(path, "utf8"));
    return typeof parsed === "object" && parsed !== null ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Does an artifact's stamp describe the source that is checked out right now?
 *
 * Deliberately compares `treeHash` ONLY. Comparing `commit` as well would make a
 * stamp built from identical source but a different commit id (a rebase, a
 * cherry-pick) read as stale, which trains people to ignore the check. Comparing
 * timestamps would make it nondeterministic. The tree hash is the whole claim.
 */
export function stampAgrees(artifactStamp, worktree) {
  if (artifactStamp === null || artifactStamp === undefined) {
    return { agree: false, reason: "no stamp — the artifact was built before stamping existed, or not built at all" };
  }
  if (typeof artifactStamp.unavailable === "string") {
    return { agree: false, reason: `artifact was built without provenance (${artifactStamp.unavailable})` };
  }
  if (artifactStamp.repo !== worktree.repo) {
    return { agree: false, reason: `stamp is from repo ${artifactStamp.repo}, working tree is ${worktree.repo}` };
  }
  if (artifactStamp.treeHash !== worktree.treeHash) {
    return {
      agree: false,
      reason: `built from tree ${short(artifactStamp.treeHash)}, working tree is ${short(worktree.treeHash)} — rebuild it`,
    };
  }
  return { agree: true, reason: "" };
}

/**
 * Compare an artifact stamp against the working tree, measured with the
 * ARTIFACT'S OWN declared scope.
 *
 * This is the single call `--assert` makes per artifact. Recomputing with the
 * artifact's `roots` — rather than a scope the caller chose — is what stops the
 * check from being a different question than the one the stamp answers. That
 * substitution (two accurate measurements of different questions) is the
 * original sin this whole mechanism exists to prevent.
 */
export function verifyArtifact(artifactStamp) {
  if (artifactStamp === null || artifactStamp === undefined) {
    return { agree: false, reason: "no stamp — not built, or built before stamping existed", stamp: null, worktree: null };
  }
  if (typeof artifactStamp.unavailable === "string") {
    return { agree: false, reason: `artifact was built without provenance (${artifactStamp.unavailable})`, stamp: artifactStamp, worktree: null };
  }
  const repo = artifactStamp.repo ?? "core-foundation";
  const worktree = worktreeStamp({
    repo,
    repoRoot: REPO_PATHS[repo],
    artifact: artifactStamp.artifact ?? "worktree",
    roots: Array.isArray(artifactStamp.roots) && artifactStamp.roots.length > 0 ? artifactStamp.roots : undefined,
  });
  return { ...stampAgrees(artifactStamp, worktree), stamp: artifactStamp, worktree };
}

export function short(hash) {
  return typeof hash === "string" ? hash.slice(0, 12) : String(hash);
}

/** One-line human form used in shell output and the ACCEPTANCE line. */
export function formatStamp(stamp) {
  if (!stamp) return "(none)";
  return `${stamp.repo}@${short(stamp.commit)}/tree:${short(stamp.treeHash)}${stamp.dirty ? "+dirty" : ""}`;
}

// ── CLI ─────────────────────────────────────────────────────────────────────
// `node integration/lib/provenance.mjs [--repo <name>] [--artifact <name>]
//                                      [--out <file>] [--workspace]`
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const argv = process.argv.slice(2);
  const flag = (name) => {
    const i = argv.indexOf(name);
    return i === -1 ? undefined : argv[i + 1];
  };
  const stamp = argv.includes("--workspace")
    ? workspaceStamps({ artifact: flag("--artifact") ?? "worktree" })
    : worktreeStamp({ repo: flag("--repo") ?? "core-foundation", artifact: flag("--artifact") ?? "worktree" });
  const out = flag("--out");
  const text = `${JSON.stringify(stamp, null, 2)}\n`;
  if (out) writeFileSync(out, text);
  process.stdout.write(text);
}
