#!/usr/bin/env node
/**
 * Production type-scale fence: `font-size` in
 * `packages/surfaces/src/production/**` must use a token (or a relative unit),
 * never an absolute length.
 *
 * `src/dev/**` and `src/lab/**` are not production surfaces and are exempt.
 *
 * Relative units (`%`, `em`, `rem`, keywords, `var(...)`) are out of scope.
 * `font-size: 200%` on the polish-evidence accessibility selector scales the
 * whole document for a QA matrix; it is not a second undeclared type scale.
 * Absolute lengths (`px`, `pt`, and the rest of the CSS absolute set) are the
 * bypass this fence exists to catch.
 */
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const PRODUCTION_CSS = join(ROOT, "packages/surfaces/src/production");
const FONT_SIZE_DECL = /font-size\s*:\s*([^;}{]+)/gi;
const ABSOLUTE_LENGTH = /(?:^|[^\w-])(\d*\.?\d+)(px|pt|pc|in|cm|mm|q)\b/i;

function stripCommentsPreservingLines(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, " "));
}

function lineNumberAt(source, index) {
  let line = 1;
  for (let i = 0; i < index; i++) if (source.charCodeAt(i) === 10) line += 1;
  return line;
}

export function findAbsoluteFontSizes(source, label) {
  const stripped = stripCommentsPreservingLines(source);
  const hits = [];
  FONT_SIZE_DECL.lastIndex = 0;
  let match;
  while ((match = FONT_SIZE_DECL.exec(stripped))) {
    const value = match[1].trim();
    if (!ABSOLUTE_LENGTH.test(value)) continue;
    hits.push({
      file: label,
      line: lineNumberAt(stripped, match.index),
      value,
    });
  }
  return hits;
}

function walkCss(dir) {
  const files = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) files.push(...walkCss(full));
    else if (name.endsWith(".css")) files.push(full);
  }
  return files;
}

const SELF_TESTS = [
  {
    name: "a reintroduced pixel font-size fails",
    css: "html[data-platform=\"desktop\"] .x { font-size: 12px; }\n",
    mustFail: true,
  },
  {
    name: "a tokenized font-size passes",
    css: ".x { font-size: var(--type-label-size); }\n",
    mustFail: false,
  },
  {
    name: "relative 200% accessibility scale is out of scope",
    css: "html[data-polish-evidence=\"true\"] { font-size: 200%; }\n",
    mustFail: false,
  },
  {
    name: "inherit is out of scope",
    css: ".x { font-size: inherit; }\n",
    mustFail: false,
  },
];

const selfTestFailures = [];
const scratch = mkdtempSync(join(tmpdir(), "omi-type-scale-"));
try {
  for (const fixture of SELF_TESTS) {
    const file = join(scratch, `${fixture.name.replaceAll(" ", "-")}.css`);
    writeFileSync(file, fixture.css);
    const hits = findAbsoluteFontSizes(readFileSync(file, "utf8"), file);
    const failed = hits.length > 0;
    if (failed !== fixture.mustFail) {
      selfTestFailures.push(
        `self-test "${fixture.name}": expected ${fixture.mustFail ? "FAIL" : "PASS"}, `
          + `it ${failed ? "failed" : "passed"} (${hits.map((hit) => hit.value).join(", ") || "no hits"})`,
      );
    }
  }
} finally {
  rmSync(scratch, { recursive: true, force: true });
}

if (selfTestFailures.length) {
  console.error(`production type-scale fence IS ITSELF BROKEN (${selfTestFailures.length}):`);
  for (const failure of selfTestFailures) console.error(`  ${failure}`);
  process.exit(1);
}

const productionHits = walkCss(PRODUCTION_CSS).flatMap((file) =>
  findAbsoluteFontSizes(readFileSync(file, "utf8"), relative(join(ROOT, ".."), file)),
);

if (productionHits.length) {
  console.error(`production type-scale fence FAILED (${productionHits.length}):`);
  for (const hit of productionHits) {
    console.error(`  ${hit.file}:${hit.line} font-size: ${hit.value}`);
  }
  process.exit(1);
}

console.log(
  "production type-scale fence passed "
    + `(packages/surfaces/src/production/**/*.css; ${SELF_TESTS.length} self-test fixtures green).`,
);
