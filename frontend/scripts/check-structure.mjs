#!/usr/bin/env node
// Enforces core/ workspace structure rules. Run in CI and pre-commit.
//
// Rule 1: no workspace dependency cycles among @omi-core/* packages
//         (dependencies + devDependencies in packages/*/package.json + contracts/package.json).
// Rule 2: no *.test.ts outside their home — tests for contracts, domain, sync, kernel,
//         and both adapter packages live in packages/testkit/ (testkit/src/** and surfaces/**
//         are exempt).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const WORKSPACE_PREFIX = "@omi-core/";
const failures = [];

// ── Rule 1: workspace dependency cycles ──────────────────────────────────────

function readWorkspaceDeps(pkgPath) {
  const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
  const deps = new Set();
  for (const field of ["dependencies", "devDependencies"]) {
    const block = pkg[field];
    if (!block) continue;
    for (const [name, spec] of Object.entries(block)) {
      if (name.startsWith(WORKSPACE_PREFIX)) deps.add(name);
    }
  }
  return { name: pkg.name, deps };
}

const graph = new Map(); // name → Set<depName>

for (const rel of ["contracts/package.json", ...readdirSync(join(ROOT, "packages")).map((d) => `packages/${d}/package.json`)]) {
  const full = join(ROOT, rel);
  if (!statSync(full).isFile()) continue;
  const { name, deps } = readWorkspaceDeps(full);
  if (!name.startsWith(WORKSPACE_PREFIX)) continue;
  graph.set(name, deps);
}

// DFS cycle detection — returns cycle path or null
function findCycle() {
  const visited = new Set();
  const stack = new Set();
  const path = [];

  function dfs(node) {
    if (stack.has(node)) {
      const start = path.indexOf(node);
      return path.slice(start).concat(node);
    }
    if (visited.has(node)) return null;
    visited.add(node);
    stack.add(node);
    path.push(node);
    for (const dep of graph.get(node) ?? []) {
      const cycle = dfs(dep);
      if (cycle) return cycle;
    }
    path.pop();
    stack.delete(node);
    return null;
  }

  for (const node of graph.keys()) {
    const cycle = dfs(node);
    if (cycle) return cycle;
  }
  return null;
}

const cycle = findCycle();
if (cycle) {
  failures.push(
    `workspace dependency cycle: ${cycle.join(" → ")} (rule 1)`
  );
}

// ── Rule 2: test files outside their home ────────────────────────────────────

const FORBIDDEN_TEST_ROOTS = [
  "contracts/src",
  "packages/domain/src",
  "packages/sync/src",
  "packages/kernel/src",
  "packages/adapters-legacy/src",
  "packages/adapters-platform/src",
];

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name === ".turbo") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (name.endsWith(".test.ts")) yield p;
  }
}

for (const root of FORBIDDEN_TEST_ROOTS) {
  const dir = join(ROOT, root);
  if (!statSync(dir).isDirectory()) continue;
  for (const file of walk(dir)) {
    const rel = relative(ROOT, file);
    failures.push(
      `${rel}: test file outside packages/testkit/ — move to testkit (rule 2)`
    );
  }
}

// ── Report ───────────────────────────────────────────────────────────────────

if (failures.length) {
  console.error(`core/ structure check FAILED (${failures.length}):`);
  for (const f of failures) console.error("  " + f);
  process.exit(1);
}
console.log("core/ structure check passed.");
