#!/usr/bin/env node
// Deterministic Wave 0 i18n ratchet. Run after the workspace build so the
// checker validates the package's emitted public API, then inspect source text
// for duplicate canonical keys (which an object import would hide).
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";

// TypeScript is a dev dependency of the workspace. The fallback keeps this
// checker usable in a pnpm checkout where the virtual-store symlink has not
// been materialized yet, without weakening the AST guard to a regex scrape.
let ts;
try {
  ts = await import("typescript");
} catch {
  const virtualStore = join(dirname(fileURLToPath(import.meta.url)), "..", "node_modules", ".pnpm");
  const candidate = readdirSync(virtualStore).find((name) => name.startsWith("typescript@"));
  if (!candidate) throw new Error("i18n parity: TypeScript parser unavailable; install workspace dev dependencies");
  ts = await import(new URL(`file://${join(virtualStore, candidate, "node_modules", "typescript", "lib", "typescript.js")}`).href);
}

const root = fileURLToPath(new URL("..", import.meta.url));
const i18nRoot = join(root, "packages", "i18n");
const distEntry = join(i18nRoot, "dist", "index.js");
const sourceCatalog = join(i18nRoot, "src", "catalog.ts");
const expectedLocales = [
  "ar",
  "be",
  "bg",
  "bn",
  "bs",
  "ca",
  "cs",
  "da",
  "de",
  "el",
  "en",
  "es",
  "et",
  "fa",
  "fi",
  "fr",
  "he",
  "hi",
  "hr",
  "hu",
  "id",
  "it",
  "ja",
  "kn",
  "ko",
  "lt",
  "lv",
  "mk",
  "mr",
  "ms",
  "nl",
  "no",
  "pl",
  "pt",
  "ro",
  "ru",
  "sk",
  "sl",
  "sr",
  "sv",
  "ta",
  "te",
  "th",
  "tl",
  "tr",
  "uk",
  "ur",
  "vi",
  "zh",
];

const errors = [];
const warnings = [];

if (!existsSync(distEntry)) {
  console.error("i18n parity: missing packages/i18n/dist; run `pnpm --filter @omi-core/i18n build` first");
  process.exit(1);
}

const api = await import(new URL(`file://${distEntry}`).href);
const locales = [...api.SUPPORTED_LOCALES];
if (locales.length !== 49) errors.push(`supported locale count is ${locales.length}; expected 49`);
if (new Set(locales).size !== locales.length) errors.push("supported locale IDs contain duplicates");
if (JSON.stringify(locales) !== JSON.stringify(expectedLocales)) {
  errors.push("supported locale IDs differ from the legacy English+48 identity");
}

const translated = [...api.TRANSLATED_LOCALES];
if (JSON.stringify(translated) !== JSON.stringify(["en"])) {
  errors.push(`translated locale set is ${JSON.stringify(translated)}; Wave 0 permits only ["en"]`);
}
const fallback = [...api.FALLBACK_LOCALES];
if (fallback.length !== 48) errors.push(`fallback locale count is ${fallback.length}; expected 48`);
if (new Set([...translated, ...fallback]).size !== 49) {
  errors.push("translated and fallback locale sets do not partition the 49 supported IDs");
}

const messages = api.EN_MESSAGES;
const runtimeKeys = Object.keys(messages);
const source = readFileSync(sourceCatalog, "utf8");
const sourceKeys = [...source.matchAll(/^  "([^"\\]+)":/gm)].map((match) => match[1]);
const sourceDuplicates = sourceKeys.filter((key, index) => sourceKeys.indexOf(key) !== index);
if (sourceDuplicates.length > 0) {
  errors.push(`canonical catalog defines duplicate keys: ${[...new Set(sourceDuplicates)].join(", ")}`);
}
if (new Set(sourceKeys).size !== runtimeKeys.length || sourceKeys.some((key) => !runtimeKeys.includes(key))) {
  errors.push("canonical source keys and emitted EN_MESSAGES keys differ");
}
for (const key of runtimeKeys) {
  const value = messages[key];
  if (typeof value !== "string" || value.trim() === "") errors.push(`canonical message ${key} is empty or not a string`);
  if (!/^[a-z][A-Za-z0-9]*(?:\.[a-z][A-Za-z0-9]*)+$/.test(key)) {
    errors.push(`canonical key ${key} is not namespace-qualified`);
  }
  const braces = value.match(/[{}]/g) ?? [];
  if (braces.length % 2 !== 0) errors.push(`canonical message ${key} has unbalanced braces`);
  const names = [...value.matchAll(/\{([A-Za-z][A-Za-z0-9_.-]*)\}/g)].map((match) => match[1]);
  if (new Set(names).size !== names.length) warnings.push(`${key} repeats an interpolation placeholder`);
  const variables = Object.fromEntries(names.map((name) => [name, `__${name}__`]))
  try {
    const rendered = names.length ? api.t("en", key, variables) : api.t("en", key);
    if (/\{[A-Za-z][A-Za-z0-9_.-]*\}/.test(rendered)) errors.push(`${key} leaves an interpolation token unresolved`);
  } catch (error) {
    errors.push(`${key} cannot be safely interpolated: ${error instanceof Error ? error.message : String(error)}`);
  }
}

const productionRoot = join(root, "packages", "surfaces", "src", "production");
if (existsSync(productionRoot)) {
  const files = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const absolute = join(directory, entry.name);
      if (entry.isDirectory()) visit(absolute);
      else if (/\.(css|jsx?|tsx?)$/.test(entry.name)) files.push(absolute);
    }
  };
  visit(productionRoot);
  for (const file of files) {
    const contents = readFileSync(file, "utf8");
    const sourceFile = ts.createSourceFile(
      file,
      contents,
      ts.ScriptTarget.Latest,
      true,
      /\.tsx?$/.test(file) ? ts.ScriptKind.TSX : ts.ScriptKind.JSX,
    );
    const isSafeAttribute = (name) =>
      name === "className" || name === "class" || name === "id" || name === "role" || name === "aria-current" ||
      name === "aria-hidden" || name === "aria-disabled" || name === "aria-live" ||
      name === "name" || name === "type" || name === "value" || name === "href" ||
      name === "src" || name === "style" || name === "key" || name === "active" || name === "placement" ||
      name === "aria-labelledby" || name === "d" || name === "viewBox" || name === "focusable" || name.startsWith("data-");
    const isNonCopyLiteral = (value) => /^[+×★☆]$/.test(value.trim());
    const reportVisibleLiteral = (node, context) => {
      const line = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1;
      const relative = file.startsWith(`${root}/`) ? file.slice(root.length + 1) : file;
      errors.push(`production surface ${relative}:${line} embeds visible string ${context}; call t()`);
    };
    const visitAst = (node) => {
      if (ts.isJsxText(node)) {
        if (node.getText(sourceFile).trim() !== "" && !isNonCopyLiteral(node.getText(sourceFile))) reportVisibleLiteral(node, "JSX text");
      } else if (ts.isJsxAttribute(node)) {
        const name = node.name.getText(sourceFile);
        const initializer = node.initializer;
        if (!isSafeAttribute(name) && initializer) {
          if (ts.isStringLiteral(initializer) && !isNonCopyLiteral(initializer.text)) reportVisibleLiteral(initializer, `attribute ${name}`);
          else if (ts.isJsxExpression(initializer) && initializer.expression) {
            const expression = initializer.expression;
            if ((ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) && !isNonCopyLiteral(expression.text)) {
              reportVisibleLiteral(expression, `attribute ${name}`);
            }
          }
        }
      } else if (ts.isJsxExpression(node) && node.expression) {
        const expression = node.expression;
        const attribute = ts.isJsxAttribute(node.parent) ? node.parent : undefined;
        const attributeName = attribute?.name.getText(sourceFile);
        if ((!attribute || !isSafeAttribute(attributeName)) &&
            (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) && !isNonCopyLiteral(expression.text)) {
          reportVisibleLiteral(expression, "JSX expression");
        }
      }
      ts.forEachChild(node, visitAst);
    };
    // red-proof: mutating a production JSX child from t("...") to "..."
    // must add an error even when the canonical English text is not in catalog.
    visitAst(sourceFile);
  }
} else {
  warnings.push("hardcoded-copy check skipped: packages/surfaces/src/production/ does not exist yet");
}

const coverage = api.getTranslationCoverage();
console.log(
  `i18n parity: ${coverage.supportedLocaleCount} supported locales; ` +
    `${coverage.translatedLocaleCount} translated; ${coverage.fallbackLocaleCount} explicit English fallbacks; ` +
    `${runtimeKeys.length} canonical messages`,
);
for (const warning of warnings) console.warn(`i18n parity warning: ${warning}`);
if (errors.length > 0) {
  for (const error of errors) console.error(`i18n parity error: ${error}`);
  process.exit(1);
}
console.log("i18n parity: pass");
