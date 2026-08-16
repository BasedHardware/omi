#!/usr/bin/env node
/**
 * Production accessible-name fence: an icon-only `button` or `a` in
 * `packages/surfaces/src/production/**` must carry `aria-label` /
 * `aria-labelledby`, or visible text / a visually-hidden name. ProductionIcon
 * is `aria-hidden`, so the parent is the name.
 *
 * `src/dev/**` and `src/lab/**` are not production surfaces and are exempt.
 */
import { mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const PRODUCTION_TSX = join(ROOT, "packages/surfaces/src/production");
const INTERACTIVE = /<(button|a)\b([^>]*?)>([\s\S]*?)<\/\1>/gi;
const ICON = /<(?:ProductionIcon|ChromeIcon)\b/;

function lineNumberAt(source, index) {
  let line = 1;
  for (let i = 0; i < index; i++) if (source.charCodeAt(i) === 10) line += 1;
  return line;
}

function stripJsxComments(source) {
  return source.replace(/\{\/\*[\s\S]*?\*\/\}/g, " ");
}

function hasAccessibleText(body) {
  const withoutIcons = body
    .replace(/<(?:ProductionIcon|ChromeIcon)\b[^>]*\/>/g, "")
    .replace(/<(?:ProductionIcon|ChromeIcon)\b[\s\S]*?<\/(?:ProductionIcon|ChromeIcon)>/g, "");
  const namedHidden = withoutIcons.replace(
    /<span\b[^>]*className=\{?["'`][^"'`]*visually-hidden[^"'`]*["'`]\}?[^>]*>[\s\S]*?<\/span>/g,
    "NAME",
  );
  const withoutTags = namedHidden.replace(/<[^>]+>/g, " ");
  const namedJsx = withoutTags.replace(/\{[\s\S]*?\}/g, (expr) => {
    if (ICON.test(expr)) return "";
    if (/\bt\(|\btranslate\(|\blabel\b|\bchildren\b|["'`][^"'`]+["'`]/.test(expr)) return "NAME";
    return "";
  });
  return namedJsx.replace(/\s+/g, "").length > 0;
}

export function findIconOnlyNameIssues(source, label) {
  const stripped = stripJsxComments(source);
  const hits = [];
  INTERACTIVE.lastIndex = 0;
  let match;
  while ((match = INTERACTIVE.exec(stripped))) {
    const attrs = match[2];
    const body = match[3];
    if (!ICON.test(body)) continue;
    if (/\baria-label\s*=/.test(attrs) || /\baria-labelledby\s*=/.test(attrs)) continue;
    if (hasAccessibleText(body)) continue;
    hits.push({
      file: label,
      line: lineNumberAt(stripped, match.index),
      snippet: match[0].replace(/\s+/g, " ").slice(0, 180),
    });
  }
  return hits;
}

function walkTsx(dir) {
  const files = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) files.push(...walkTsx(full));
    else if (name.endsWith(".tsx")) files.push(full);
  }
  return files;
}

const SELF_TESTS = [
  {
    name: "an icon-only button without aria-label fails",
    tsx: `<button type="button"><ProductionIcon name="plus" /></button>\n`,
    mustFail: true,
  },
  {
    name: "an icon-only button with aria-label passes",
    tsx: `<button type="button" aria-label={t(locale, "tasks.add")}><ProductionIcon name="plus" /></button>\n`,
    mustFail: false,
  },
  {
    name: "an icon plus visible text passes without aria-label",
    tsx: `<a href="/x"><ChromeIcon name="home" /><span className="nav-label">{t(locale, "nav.home")}</span></a>\n`,
    mustFail: false,
  },
];

function runSelfTests() {
  const failures = [];
  const scratch = mkdtempSync(join(tmpdir(), "omi-a11y-names-"));
  try {
    for (const fixture of SELF_TESTS) {
      const file = join(scratch, `${fixture.name.replaceAll(" ", "-")}.tsx`);
      writeFileSync(file, fixture.tsx);
      const hits = findIconOnlyNameIssues(readFileSync(file, "utf8"), file);
      const failed = hits.length > 0;
      if (failed !== fixture.mustFail) {
        failures.push(
          `self-test "${fixture.name}": expected ${fixture.mustFail ? "FAIL" : "PASS"}, `
            + `it ${failed ? "failed" : "passed"} (${hits.map((hit) => hit.snippet).join("; ") || "no hits"})`,
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
    console.error(`accessibility names fence IS ITSELF BROKEN (${selfTestFailures.length}):`);
    for (const failure of selfTestFailures) console.error(`  ${failure}`);
    process.exit(1);
  }

  const productionHits = walkTsx(PRODUCTION_TSX).flatMap((file) =>
    findIconOnlyNameIssues(readFileSync(file, "utf8"), relative(join(ROOT, ".."), file)),
  );
  if (productionHits.length) {
    console.error(`accessibility names fence FAILED (${productionHits.length}):`);
    for (const hit of productionHits) {
      console.error(`  ${hit.file}:${hit.line} ${hit.snippet}`);
    }
    process.exit(1);
  }

  console.log(
    "accessibility names fence passed "
      + `(packages/surfaces/src/production/**/*.tsx; ${SELF_TESTS.length} self-test fixtures green).`,
  );
}
