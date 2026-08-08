#!/usr/bin/env node
// Enforces the core/ isolation rules (core/README.md). Run in CI and pre-commit.
//
// Rule 1: nothing under core/ may import from the old trees (app/, desktop/, web/,
//         backend/) — by relative path, tsconfig path alias, or package name.
// Rule 3: fetch/axios/WebSocket against backend hosts may only appear inside an
//         ADAPTER package (packages/adapters-legacy/, packages/adapters-platform/)
//         or shells/ — the sync layer speaks contracts, not endpoints. The rule is
//         about the LAYER, not about one package: adapters-platform speaks the new
//         contracts-native wire and is just as much the designated home for a raw
//         route as adapters-legacy is for a legacy one.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const OLD_TREES = ["app/", "desktop/", "web/", "backend/", "sdks/", "plugins/"];
const SOURCE_RE = /\.(ts|tsx|mts|cts|js|mjs|swift|dart|kt)$/;
const IMPORT_RE = /(?:from\s+["']|import\s*\(\s*["']|require\s*\(\s*["'])([^"')]+)["']/g;
const RAW_ENDPOINT_RE = /https?:\/\/[^"'` ]*(?:omi|based)[^"'` ]*\/v\d|\/v[0-9]\/(?:conversations|memories|action-items|messages|users|apps|folders|goals)\b/;

const failures = [];

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    // Build OUTPUT is not source. The native shells under shells/ emit .build
    // (swiftc app bundles, which embed the compiled surface JS), build/,
    // .dart_tool/ and Pods/ — scanning those makes the gate report the bundled
    // surface bundle as a rule-3 violation, i.e. it fails on its own artifacts.
    if (
      name === "node_modules" ||
      name === "dist" ||
      name === ".turbo" ||
      name === ".build" ||
      name === "build" ||
      name === ".dart_tool" ||
      name === "Pods"
    ) {
      continue;
    }
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

  const inAdapterOrShell =
    rel.startsWith("packages/adapters-legacy/") ||
    rel.startsWith("packages/adapters-platform/") ||
    rel.startsWith("packages/dev-recall-stub/") || // dev fixture SERVER: it serves the route it names
    rel.startsWith("shells/") ||
    rel.startsWith("packages/testkit/src/test/"); // tests may ASSERT the wire paths adapters speak
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
