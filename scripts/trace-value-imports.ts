/**
 * Print the transitive VALUE-import closure of one or more entrypoints, and
 * optionally flag modules that must not appear in it.
 *
 * WHY THIS EXISTS, AND WHY IT IS NOT YET A FENCE.
 *
 * `lint-import-graph.ts` enforces two rules: the port registry (16) and the
 * wire-path fence (17). Neither asks the question "what does the production
 * kernel actually link?" Two defects of exactly that shape have now shipped
 * past it:
 *
 *   1. `apps/service/composition/memory-read.ts` value-imported `apps/qa/renders`,
 *      pulling `createQaDeterministicSynthesizer` -- a MODEL FAKE -- onto the
 *      production graph. Found by building the image, not by lint. It was
 *      reached by two distinct chains; a hand trace found only one.
 *   2. `apps/service/workers/predicate-batch-contract.ts` value-imported
 *      `predicateAlignmentPromptCost` from `drivers/model/glm`, linking the GLM
 *      client into every image running predicate-batch consolidation.
 *
 * Both were invisible to lint and both were found by tracing the closure. This
 * script is that trace, made repeatable. Promoting it to a rule-18 fence -- with
 * a ratified list of entrypoints and forbidden targets -- is the obvious next
 * step, but adding a CI gate is a design decision, so this ships as a diagnostic
 * and the fence stays a proposal.
 *
 * TYPE-ONLY IMPORTS ARE EXCLUDED. They erase at runtime and cannot link
 * anything into an image, so counting them would produce false positives that
 * teach people to ignore the output -- the failure mode that kills fences.
 *
 * Usage:
 *   bun run scripts/trace-value-imports.ts <entry.ts> [more-entries...]
 *     [--forbid <substring>] [--list]
 *
 * Exits non-zero if any --forbid substring appears in a closure.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";

const PROJECT_ROOT = resolve(import.meta.dir, "..");

const resolveSpecifier = (fromFile: string, specifier: string): string | null => {
  if (!specifier.startsWith(".")) return null;
  const base = resolve(dirname(fromFile), specifier);
  for (const candidate of [`${base}.ts`, `${base}/index.ts`, base]) {
    if (candidate.endsWith(".ts") && existsSync(candidate)) return candidate;
  }
  return null;
};

const IMPORT_PATTERN = /import\s+(type\s+)?([\s\S]*?)from\s*["']([^"']+)["']/g;

/** True when the clause binds at least one runtime name. */
const bindsRuntimeValue = (typeKeyword: boolean, clause: string): boolean => {
  if (typeKeyword) return false;
  const names = clause.replace(/[{}]/g, " ").split(",").map((part) => part.trim()).filter(Boolean);
  if (names.length === 0) return true; // bare side-effect or default import
  return names.some((name) => !name.startsWith("type "));
};

const trace = (entry: string): { seen: Set<string>; parent: Map<string, string> } => {
  const seen = new Set<string>([entry]);
  const parent = new Map<string, string>();
  const queue = [entry];
  while (queue.length > 0) {
    const file = queue.shift()!;
    let text: string;
    try { text = readFileSync(file, "utf8"); } catch { continue; }
    for (const match of text.matchAll(IMPORT_PATTERN)) {
      if (!bindsRuntimeValue(Boolean(match[1]), match[2] ?? "")) continue;
      const target = resolveSpecifier(file, match[3]!);
      if (target === null || seen.has(target)) continue;
      seen.add(target);
      parent.set(target, file);
      queue.push(target);
    }
  }
  return { seen, parent };
};

const chain = (parent: Map<string, string>, file: string): string[] => {
  const path: string[] = [];
  let current: string | undefined = file;
  while (current !== undefined) {
    path.unshift(relative(PROJECT_ROOT, current));
    current = parent.get(current);
  }
  return path;
};

const argv = process.argv.slice(2);
const forbidden: string[] = [];
const entries: string[] = [];
let list = false;
for (let index = 0; index < argv.length; index += 1) {
  const argument = argv[index]!;
  if (argument === "--forbid") { forbidden.push(argv[index + 1]!); index += 1; }
  else if (argument === "--list") list = true;
  else entries.push(argument);
}

if (entries.length === 0) {
  console.error("usage: bun run scripts/trace-value-imports.ts <entry.ts> [--forbid <substring>] [--list]");
  process.exit(2);
}

let violations = 0;
for (const entry of entries) {
  const absolute = resolve(PROJECT_ROOT, entry);
  if (!existsSync(absolute)) { console.error(`missing entry: ${entry}`); process.exit(2); }
  const { seen, parent } = trace(absolute);
  console.log(`\n=== ${entry} — ${seen.size} runtime-linked modules ===`);
  if (list) {
    for (const file of [...seen].map((f) => relative(PROJECT_ROOT, f)).sort()) console.log(`  ${file}`);
  }
  for (const needle of forbidden) {
    const hits = [...seen].filter((file) => relative(PROJECT_ROOT, file).includes(needle));
    if (hits.length === 0) { console.log(`  ok: no "${needle}"`); continue; }
    violations += hits.length;
    for (const hit of hits) {
      console.log(`  FORBIDDEN "${needle}": ${relative(PROJECT_ROOT, hit)}`);
      console.log(`    ${chain(parent, hit).join("\n      -> ")}`);
    }
  }
}

if (violations > 0) {
  console.error(`\n${violations} forbidden module(s) on a production closure`);
  process.exit(1);
}
