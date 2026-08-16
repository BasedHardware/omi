#!/usr/bin/env node
// Exact-match freshness for the macOS .app the launcher would otherwise rebuild.
//
// Skip is allowed only when BOTH are true:
//   1. Contents/Resources/omi-build-stamp.json agrees with the current
//      working tree (integration/lib/provenance.mjs — the same stamp
//      build-shell.sh writes; treeHash only, no mtimes, no heuristics).
//   2. The sha256 of every file under OMI_SURFACES_DIST equals the sha256 of
//      Contents/Resources/surface/ — the copy rsync lands in the bundle.
//      A Swift-only tree hash would miss a dist rebuild, which is how a
//      stale surface gets served from an otherwise "fresh" shell.
//
// Anything else — missing bundle, unavailable stamp, hasher failure, one
// byte of difference — is a rebuild. Uncertainty never skips.
//
// This file does not change build-shell.sh. Direct compilers and verification
// lanes that invoke build-shell.sh still always compile. run-shell.sh is the
// only caller that consults this, and even there a checker failure rebuilds.

import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const MACOS_ROOT = resolve(HERE, "..");
const REPO_ROOT = resolve(MACOS_ROOT, "../../..");

export function shellStampPath(app) {
  return join(app, "Contents/Resources/omi-build-stamp.json");
}

export function bundledSurfaceDir(app) {
  return join(app, "Contents/Resources/surface");
}

export function posixRel(root, abs) {
  return relative(root, abs).split(sep).join("/");
}

/** Content hash of a directory tree. Paths are relative and sorted. No mtimes. */
export function hashTree(root) {
  if (!existsSync(root)) {
    throw new Error(`hashTree: ${root} does not exist`);
  }
  const files = [];
  const entries = readdirSync(root, { withFileTypes: true, recursive: true });
  for (const ent of entries) {
    if (!ent.isFile()) continue;
    const dir = ent.parentPath ?? ent.path ?? root;
    files.push(join(dir, ent.name));
  }
  files.sort();
  const hash = createHash("sha256");
  for (const abs of files) {
    hash.update(posixRel(root, abs));
    hash.update("\0");
    hash.update(readFileSync(abs));
    hash.update("\0");
  }
  return hash.digest("hex");
}

export function shortHash(value) {
  return typeof value === "string" ? value.slice(0, 12) : String(value);
}

export function defaultSurfacesDist() {
  for (const candidate of [
    join(MACOS_ROOT, "../../packages/surfaces/dist"),
    join(MACOS_ROOT, "../../../frontend/packages/surfaces/dist"),
  ]) {
    if (existsSync(join(candidate, "index.html"))) return resolve(candidate);
  }
  return "";
}

/**
 * @param {{ app: string, dist: string, readStampFile: Function, verifyArtifact: Function }} args
 * @returns {{ fresh: boolean, reason: string }}
 */
export function freshness({ app, dist, readStampFile, verifyArtifact }) {
  if (!app || !existsSync(app)) {
    return { fresh: false, reason: "no app bundle — rebuild it" };
  }
  const stamp = readStampFile(shellStampPath(app));
  const verified = verifyArtifact(stamp);
  if (!verified.agree) {
    return { fresh: false, reason: verified.reason || "macos-app stamp does not agree — rebuild it" };
  }
  if (!dist || !existsSync(join(dist, "index.html"))) {
    return { fresh: false, reason: "surfaces dist missing; set OMI_SURFACES_DIST — rebuild it" };
  }
  const bundled = bundledSurfaceDir(app);
  if (!existsSync(join(bundled, "index.html"))) {
    return { fresh: false, reason: "bundled surface missing — rebuild it" };
  }
  let distHash;
  let bundledHash;
  try {
    distHash = hashTree(dist);
    bundledHash = hashTree(bundled);
  } catch (error) {
    return {
      fresh: false,
      reason: `could not hash surfaces (${error instanceof Error ? error.message : String(error)}) — rebuild it`,
    };
  }
  if (distHash !== bundledHash) {
    return {
      fresh: false,
      reason:
        `bundled surfaces ${shortHash(bundledHash)}, working dist ${shortHash(distHash)} — rebuild it`,
    };
  }
  const tree = stamp?.treeHash;
  return {
    fresh: true,
    reason:
      `macos-app tree ${shortHash(tree)} matches working tree; surfaces sha256=${shortHash(distHash)} matches bundled copy`,
  };
}

async function loadProvenance() {
  return import(resolve(REPO_ROOT, "integration/lib/provenance.mjs"));
}

export async function checkBundle({ app, dist }) {
  const { readStampFile, verifyArtifact } = await loadProvenance();
  return freshness({ app, dist, readStampFile, verifyArtifact });
}

function parseArgs(argv) {
  const flag = (name) => {
    const i = argv.indexOf(name);
    return i === -1 ? undefined : argv[i + 1];
  };
  return {
    app: flag("--app"),
    dist: flag("--dist"),
  };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const args = parseArgs(process.argv.slice(2));
  if (!args.app) {
    process.stderr.write("usage: node shell-bundle-fresh.mjs --app <path.app> [--dist <surfaces-dist>]\n");
    process.exit(2);
  }
  const dist = args.dist && args.dist.length > 0 ? resolve(args.dist) : defaultSurfacesDist();
  const result = await checkBundle({ app: resolve(args.app), dist });
  if (result.fresh) {
    process.stdout.write(`cached: ${result.reason}\n`);
    process.exit(0);
  }
  process.stdout.write(`rebuild: ${result.reason}\n`);
  process.exit(1);
}
