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
const INTERACTIVE_OPEN = /<(button|a)\b/gi;
const ICON = /<(?:ProductionIcon|ChromeIcon)\b/;

/**
 * Index of the `>` that closes this opening tag, skipping any `>` that belongs
 * to a JSX expression or a string. `[^>]*?` cannot do this: `onClick={() =>
 * ...}` ends the attribute scan at the arrow, which put the rest of the handler
 * into the element's "body" and let that text pass as an accessible name. Every
 * icon button in this tree has such a handler, so the fence saw none of them.
 */
function findOpenTagEnd(source, from) {
  let depth = 0;
  let quote = null;
  for (let i = from; i < source.length; i++) {
    const char = source[i];
    if (quote !== null) {
      if (char === "\\") i += 1;
      else if (char === quote) quote = null;
      continue;
    }
    if (char === '"' || char === "'" || char === "`") quote = char;
    else if (char === "{") depth += 1;
    else if (char === "}") depth -= 1;
    else if (char === ">" && depth === 0) return i;
  }
  return -1;
}

function* interactiveElements(source) {
  INTERACTIVE_OPEN.lastIndex = 0;
  let match;
  while ((match = INTERACTIVE_OPEN.exec(source))) {
    const tag = match[1].toLowerCase();
    const attrsStart = match.index + match[0].length;
    const openEnd = findOpenTagEnd(source, attrsStart);
    if (openEnd === -1) continue;
    INTERACTIVE_OPEN.lastIndex = openEnd + 1;
    if (source[openEnd - 1] === "/") continue;
    const closeTag = `</${tag}>`;
    const bodyEnd = source.toLowerCase().indexOf(closeTag, openEnd + 1);
    if (bodyEnd === -1) continue;
    yield {
      index: match.index,
      attrs: source.slice(attrsStart, openEnd),
      body: source.slice(openEnd + 1, bodyEnd),
      whole: source.slice(match.index, bodyEnd + closeTag.length),
    };
  }
}

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
  for (const element of interactiveElements(stripped)) {
    if (!ICON.test(element.body)) continue;
    if (/\baria-label\s*=/.test(element.attrs) || /\baria-labelledby\s*=/.test(element.attrs)) continue;
    if (hasAccessibleText(element.body)) continue;
    hits.push({
      file: label,
      line: lineNumberAt(stripped, element.index),
      snippet: element.whole.replace(/\s+/g, " ").slice(0, 180),
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
  {
    // The gap this fence shipped with: `=>` closed the attribute scan, so the
    // rest of the handler became "visible text" and named the button. Every
    // icon button in production carries an arrow handler, so the fence was
    // blind to all of them while reporting itself green.
    name: "an arrow-function handler does not smuggle a name past the fence",
    tsx: `<button type="button" onClick={() => void attach()}><ProductionIcon name="attach" /></button>\n`,
    mustFail: true,
  },
  {
    name: "an arrow-function handler with aria-label still passes",
    tsx: `<button type="button" aria-label={t(locale, "chat.attach")} onClick={() => void attach()}><ProductionIcon name="attach" /></button>\n`,
    mustFail: false,
  },
  {
    name: "a greater-than inside a string attribute does not end the tag early",
    tsx: `<button type="button" title="a > b" onClick={() => go()}><ProductionIcon name="plus" /></button>\n`,
    mustFail: true,
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
