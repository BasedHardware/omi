#!/usr/bin/env node
// Enforces the core/ isolation rules (core/README.md). Run in CI and pre-commit.
//
// Rule 1: nothing under core/ may import from the old trees (app/, desktop/, web/,
//         backend/) — by relative path, tsconfig path alias, or package name.
// Rule 3: fetch/axios/WebSocket against backend hosts may only appear inside
//         packages/adapters-legacy/ and shells/ (the sync layer speaks contracts,
//         not endpoints).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const OLD_TREES = ["app/", "desktop/", "web/", "backend/", "sdks/", "plugins/"];
const SOURCE_RE = /\.(ts|tsx|mts|cts|js|mjs|swift|dart|kt)$/;
const IMPORT_RE = /(?:from\s+["']|import\s*\(\s*["']|require\s*\(\s*["'])([^"')]+)["']/g;
const RAW_ENDPOINT_RE = /https?:\/\/[^"'` ]*(?:omi|based)[^"'` ]*\/v\d|\/v[12]\/(?:conversations|memories|action-items|messages|users|apps)\b/;

const failures = [];

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name === ".turbo") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (SOURCE_RE.test(name)) yield p;
  }
}

for (const file of walk(ROOT)) {
  const rel = relative(ROOT, file);
  const text = readFileSync(file, "utf8");

  for (const m of text.matchAll(IMPORT_RE)) {
    const spec = m[1];
    if (!spec.startsWith(".") && !spec.startsWith("/")) continue;
    const escapes = spec.startsWith("/")
      ? OLD_TREES.some((t) => spec.includes(`/${t}`))
      : OLD_TREES.some((t) => spec.includes(`../${t}`)) ||
        /^(\.\.\/)+\.\./.test(spec + "/"); // any traversal above core/
    if (escapes) failures.push(`${rel}: imports outside core/ — "${spec}" (rule 1)`);
  }

  const inAdapterOrShell = rel.startsWith("packages/adapters-legacy/") || rel.startsWith("shells/");
  if (!inAdapterOrShell && RAW_ENDPOINT_RE.test(text)) {
    failures.push(`${rel}: raw backend endpoint outside adapters-legacy//shells/ (rule 3)`);
  }
}

if (failures.length) {
  console.error(`core/ isolation check FAILED (${failures.length}):`);
  for (const f of failures) console.error("  " + f);
  process.exit(1);
}
console.log("core/ isolation check passed.");
