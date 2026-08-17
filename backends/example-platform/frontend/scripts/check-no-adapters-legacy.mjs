#!/usr/bin/env node
/**
 * Frontend production-graph fence: `@omi-core/adapters-legacy` must not return.
 *
 * THIS IS A STATIC TRIPWIRE, NOT BEHAVIOURAL COVERAGE. It traces value-import
 * closures from the production surfaces entry and fails if `adapters-legacy`
 * appears as a package, a specifier, or a resolved module. An earlier lane
 * observed that adding the package to RULE 18's *backend* forbidden list
 * would pass with the package still present, because that fence traces
 * `apps/service/bin/dev-server.ts` and the backend never imported it. The
 * real importers were `frontend/packages/domain/src/*-store.ts`. A fence
 * pointed at the wrong graph is worse than none.
 *
 * WHAT IT CATCHES:
 *   1. A value import of `@omi-core/adapters-legacy` anywhere on the
 *      production closure from `packages/surfaces/src/production/main.tsx`.
 *   2. The package directory returning under `packages/adapters-legacy`.
 *   3. A workspace package.json depending on `@omi-core/adapters-legacy`.
 *
 * Positive control: the production closure MUST include `adapters-platform`.
 * A tracer that follows nothing cannot go green.
 *
 * The self-test fixtures run on every invocation. A rename that defangs the
 * specifier match fails the self-test rather than silently passing.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = new URL("..", import.meta.url).pathname;
const ENTRY = "packages/surfaces/src/production/main.tsx";
const FORBIDDEN_PACKAGE = "adapters-legacy";
const FORBIDDEN_SPEC = "@omi-core/adapters-legacy";
const REQUIRED_PACKAGE = "adapters-platform";

const IMPORT_PATTERN =
  /(?:import\s+(type\s+)?([\s\S]*?)from\s*|import\s*\(\s*|export\s+(?:type\s+)?(?:\*|\{[\s\S]*?\})\s*from\s*)["']([^"']+)["']/g;

const bindsRuntimeValue = (typeKeyword, clause, isDynamicOrExport) => {
  if (isDynamicOrExport) return true;
  if (typeKeyword) return false;
  const names = (clause ?? "").replace(/[{}]/g, " ").split(",").map((part) => part.trim()).filter(Boolean);
  if (names.length === 0) return true;
  return names.some((name) => !name.startsWith("type "));
};

const packageSrc = new Map();
const registerPackage = (dir, srcRel) => {
  const pkgPath = join(dir, "package.json");
  if (!existsSync(pkgPath)) return;
  const pkg = JSON.parse(readFileSync(pkgPath, "utf8"));
  if (typeof pkg.name === "string") packageSrc.set(pkg.name, join(dir, srcRel));
};
registerPackage(join(ROOT, "contracts"), "src");
registerPackage(join(ROOT, "contracts/ratified"), "src");
for (const name of readdirSync(join(ROOT, "packages"))) {
  registerPackage(join(ROOT, "packages", name), "src");
}

const resolveSpecifier = (fromFile, specifier) => {
  if (specifier.startsWith(".")) {
    const base = join(dirname(fromFile), specifier.replace(/\.js$/, ""));
    for (const candidate of [
      `${base}.ts`, `${base}.tsx`, `${base}.js`, `${base}.mjs`,
      join(base, "index.ts"), join(base, "index.tsx"),
    ]) {
      if (existsSync(candidate)) return candidate;
    }
    return null;
  }
  for (const [name, src] of packageSrc) {
    if (specifier === name || specifier.startsWith(`${name}/`)) {
      const rest = specifier === name ? "" : specifier.slice(name.length + 1);
      const base = rest ? join(src, rest.replace(/\.js$/, "")) : src;
      for (const candidate of [
        `${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx"), base,
      ]) {
        if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
      }
    }
  }
  return null;
};

const trace = (entryRel) => {
  const entry = join(ROOT, entryRel);
  const seen = new Set([entry]);
  const specifiers = [];
  const parent = new Map();
  const queue = [entry];
  while (queue.length > 0) {
    const file = queue.shift();
    let text;
    try { text = readFileSync(file, "utf8"); } catch { continue; }
    for (const match of text.matchAll(IMPORT_PATTERN)) {
      const specifier = match[3];
      const isDynamic = match[0].startsWith("import(");
      const isExport = match[0].startsWith("export");
      if (!bindsRuntimeValue(Boolean(match[1]), match[2], isDynamic || isExport)) continue;
      specifiers.push({ file, specifier });
      const target = resolveSpecifier(file, specifier);
      if (target === null || seen.has(target)) continue;
      seen.add(target);
      parent.set(target, file);
      queue.push(target);
    }
  }
  return { seen, specifiers, parent };
};

const analyze = (entryRel, { packageExists = false, extraSpecifiers = [] } = {}) => {
  const failures = [];
  const { seen, specifiers } = trace(entryRel);
  const allSpecs = [...specifiers.map((row) => row.specifier), ...extraSpecifiers];
  const forbiddenHits = [...seen].filter((file) => relative(ROOT, file).includes(FORBIDDEN_PACKAGE));
  const forbiddenSpecs = [
    ...specifiers.filter((row) => row.specifier.includes(FORBIDDEN_PACKAGE) || row.specifier === FORBIDDEN_SPEC),
    ...extraSpecifiers
      .filter((spec) => spec.includes(FORBIDDEN_PACKAGE) || spec === FORBIDDEN_SPEC)
      .map((specifier) => ({ file: join(ROOT, entryRel), specifier })),
  ];
  const platformPresent = [...seen].some((file) => relative(ROOT, file).includes(REQUIRED_PACKAGE))
    || allSpecs.some((spec) => spec.includes(REQUIRED_PACKAGE));

  if (packageExists || existsSync(join(ROOT, "packages", FORBIDDEN_PACKAGE))) {
    failures.push(`packages/${FORBIDDEN_PACKAGE} exists — the retired generation package must not return`);
  }
  for (const hit of forbiddenHits) {
    failures.push(`production closure reaches ${relative(ROOT, hit)}`);
  }
  for (const row of forbiddenSpecs) {
    failures.push(`${relative(ROOT, row.file)} value-imports "${row.specifier}"`);
  }
  if (!platformPresent) {
    failures.push(
      `production closure does not reach ${REQUIRED_PACKAGE} — the tracer followed nothing `
      + "and cannot certify the forbidden package is absent",
    );
  }
  return failures;
};

const workspaceDependsOnForbidden = () => {
  const hits = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      if (name === "node_modules" || name === "dist" || name === ".turbo") continue;
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (name === "package.json") {
        const pkg = JSON.parse(readFileSync(full, "utf8"));
        for (const field of ["dependencies", "devDependencies"]) {
          if (pkg[field]?.[FORBIDDEN_SPEC]) hits.push(`${relative(ROOT, full)} depends on ${FORBIDDEN_SPEC}`);
        }
      }
    }
  };
  walk(ROOT);
  return hits;
};

const SELF_TEST_FIXTURES = [
  {
    name: "a value import of adapters-legacy on the production graph",
    extraSpecifiers: [FORBIDDEN_SPEC],
    packageExists: false,
    mustPass: false,
  },
  {
    name: "the package directory returning",
    extraSpecifiers: [],
    packageExists: true,
    mustPass: false,
  },
];

const selfTestFailures = [];
for (const fixture of SELF_TEST_FIXTURES) {
  const failures = analyze(ENTRY, fixture);
  const passed = failures.length === 0;
  if (passed !== fixture.mustPass) {
    selfTestFailures.push(
      `self-test "${fixture.name}": expected ${fixture.mustPass ? "PASS" : "FAIL"}, `
      + `it ${passed ? "passed" : "failed"}`,
    );
  }
}
if (selfTestFailures.length) {
  console.error(`frontend adapters-legacy fence IS ITSELF BROKEN (${selfTestFailures.length}):`);
  for (const failure of selfTestFailures) console.error("  " + failure);
  process.exit(1);
}

const failures = [...analyze(ENTRY), ...workspaceDependsOnForbidden()];
if (failures.length) {
  console.error(`frontend adapters-legacy fence FAILED (${failures.length}):`);
  for (const failure of failures) console.error("  " + failure);
  process.exit(1);
}
console.log(
  "frontend adapters-legacy fence passed "
  + `(production graph from ${ENTRY}; ${SELF_TEST_FIXTURES.length} self-test fixtures green).`,
);
