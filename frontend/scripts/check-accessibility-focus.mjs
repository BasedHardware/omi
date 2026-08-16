#!/usr/bin/env node
/**
 * Production focus-visible fence: every interactive control in
 * `packages/surfaces/src/production/styles.css` must use the token focus ring
 * (`--focus` / `--focus-ring-width`) on `:focus-visible`.
 *
 * Native `summary` is in the contract because Chat agent-run details are a
 * real keyboard control. An element that keeps a UA `outline: auto` while the
 * token contract exists is a bug, not a theme.
 *
 * `src/dev/**` and `src/lab/**` are not production surfaces and are exempt.
 */
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const STYLES = join(ROOT, "packages/surfaces/src/production/styles.css");

export const REQUIRED_FOCUS_ELEMENTS = [
  "input",
  "textarea",
  "select",
  "button",
  "a",
  "summary",
  '[tabindex]:not([tabindex="-1"])',
  '[role="button"]',
  '[role="option"]',
  '[role="tab"]',
  '[role="menuitem"]',
];

const TOKEN_OUTLINE = /outline\s*:\s*var\(--focus-ring-width\)\s+solid\s+var\(--focus\)/;

function extractWhereFocusContract(css) {
  const startMarker = ".production-shell :where(";
  const start = css.indexOf(startMarker);
  if (start < 0) return null;
  let index = start + startMarker.length;
  let depth = 1;
  const listFrom = index;
  while (index < css.length && depth > 0) {
    const character = css[index];
    if (character === "(") depth += 1;
    else if (character === ")") depth -= 1;
    index += 1;
  }
  if (depth !== 0) return null;
  const list = css.slice(listFrom, index - 1);
  const after = css.slice(index);
  const body = after.match(/^:focus-visible\s*\{([^}]+)\}/);
  if (!body) return null;
  return { list, body: body[1] };
}

export function findFocusContractIssues(css) {
  const issues = [];
  const where = extractWhereFocusContract(css);
  if (!where) {
    issues.push("missing .production-shell :where(...):focus-visible contract");
    return issues;
  }
  for (const element of REQUIRED_FOCUS_ELEMENTS) {
    if (!where.list.includes(element)) issues.push(`:where() omits ${element}`);
  }
  if (!TOKEN_OUTLINE.test(where.body)) {
    issues.push(":where() focus-visible outline does not use --focus / --focus-ring-width");
  }
  if (!/\.production-shell summary:focus-visible/.test(css)) {
    issues.push("missing .production-shell summary:focus-visible override");
  }
  const important = css.match(
    /\.production-shell summary:focus-visible[\s\S]{0,400}?\{([^}]+)\}/,
  );
  if (!important || !TOKEN_OUTLINE.test(important[1]) || !/!important/.test(important[1])) {
    issues.push("summary:focus-visible override does not force var(--focus) with !important");
  }
  return issues;
}

const CONTRACT_SNIPPET = `.production-shell :where(input, textarea, select, button, a, summary, [tabindex]:not([tabindex="-1"]), [role="button"], [role="option"], [role="tab"], [role="menuitem"]):focus-visible {
  outline: var(--focus-ring-width) solid var(--focus);
  outline-offset: 2px;
}
.production-shell input:focus-visible,
.production-shell textarea:focus-visible,
.production-shell select:focus-visible,
.production-shell button:focus-visible,
.production-shell a:focus-visible,
.production-shell summary:focus-visible,
.production-shell [tabindex]:not([tabindex="-1"]):focus-visible,
.production-shell [role="button"]:focus-visible,
.production-shell [role="option"]:focus-visible,
.production-shell [role="tab"]:focus-visible,
.production-shell [role="menuitem"]:focus-visible {
  outline: var(--focus-ring-width) solid var(--focus) !important;
  outline-offset: 2px !important;
}
`;

const SELF_TESTS = [
  {
    name: "dropping summary from the :where() list fails",
    css: CONTRACT_SNIPPET.replace(", summary,", ","),
    mustFail: true,
  },
  {
    name: "the full token contract including summary passes",
    css: CONTRACT_SNIPPET,
    mustFail: false,
  },
  {
    name: "a literal outline colour instead of --focus fails",
    css: CONTRACT_SNIPPET.replaceAll("var(--focus)", "#00ff00"),
    mustFail: true,
  },
];

function runSelfTests() {
  const failures = [];
  const scratch = mkdtempSync(join(tmpdir(), "omi-a11y-focus-"));
  try {
    for (const fixture of SELF_TESTS) {
      const file = join(scratch, `${fixture.name.replaceAll(" ", "-")}.css`);
      writeFileSync(file, fixture.css);
      const issues = findFocusContractIssues(readFileSync(file, "utf8"));
      const failed = issues.length > 0;
      if (failed !== fixture.mustFail) {
        failures.push(
          `self-test "${fixture.name}": expected ${fixture.mustFail ? "FAIL" : "PASS"}, `
            + `it ${failed ? "failed" : "passed"} (${issues.join("; ") || "no issues"})`,
        );
      }
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
  return failures;
}

const isMain = import.meta.url === pathToFileURL(resolve(process.argv[1] ?? "")).href;
if (isMain) {
  const selfTestFailures = runSelfTests();
  if (selfTestFailures.length) {
    console.error(`accessibility focus fence IS ITSELF BROKEN (${selfTestFailures.length}):`);
    for (const failure of selfTestFailures) console.error(`  ${failure}`);
    process.exit(1);
  }

  const productionIssues = findFocusContractIssues(readFileSync(STYLES, "utf8"));
  if (productionIssues.length) {
    console.error(`accessibility focus fence FAILED (${productionIssues.length}):`);
    for (const issue of productionIssues) console.error(`  ${issue}`);
    process.exit(1);
  }

  console.log(
    "accessibility focus fence passed "
      + `(packages/surfaces/src/production/styles.css; ${REQUIRED_FOCUS_ELEMENTS.length} controls; `
      + `${SELF_TESTS.length} self-test fixtures green).`,
  );
}
