#!/usr/bin/env node
// Lists UI strings passed to t()/i18n() in the renderer that a catalog does not
// translate yet, and catalog entries no longer used anywhere.
//
//   node scripts/i18n-report.mjs            # Spanish (default)
//   node scripts/i18n-report.mjs --json     # missing keys as a JSON object to fill in
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = fileURLToPath(new URL('../src', import.meta.url));
const lang = process.argv.find((a) => /^--lang=/.test(a))?.slice(7) ?? 'es';
const catalog = JSON.parse(readFileSync(join(root, 'lib/i18n', `${lang}.json`), 'utf8'));

function sources(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (name !== '__tests__') sources(path, out);
    } else if (/\.tsx?$/.test(name) && !/\.(test|spec|e2e)\.tsx?$/.test(name))
      out.push(path);
  }
  return out;
}

// Keys passed to t() through a variable, so the scan below cannot see them.
const RENDERED_DYNAMICALLY = [
  // DeveloperSection: SCOPE_RESOURCES, rendered through t(resource)
  'Conversations',
  'Memories',
  'Action Items',
  'Goals',
];

const isLiteral = (node) =>
  node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node));

const used = new Map(RENDERED_DYNAMICALLY.map((k) => [k, 'dynamic']));
for (const file of sources(root)) {
  const sf = ts.createSourceFile(
    file,
    readFileSync(file, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
  );
  const visit = (node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
      const [first, second] = node.arguments;
      const fn = node.expression.text;
      let key = null;
      if ((fn === 't' || fn === 'i18n') && isLiteral(first)) key = first.text;
      else if (fn === 'tc' && isLiteral(first) && isLiteral(second))
        key = `${first.text}|${second.text}`;
      if (key !== null && !used.has(key)) used.set(key, relative(root, file));
      // tn(count, one, other): both forms are catalog keys.
      if (fn === 'tn' && isLiteral(node.arguments[1]) && isLiteral(node.arguments[2])) {
        const [one, other] = [node.arguments[1].text, node.arguments[2].text];
        // Identical English forms: the singular lives under the `one|` context key.
        for (const form of one === other ? [`one|${one}`, other] : [one, other])
          if (!used.has(form)) used.set(form, relative(root, file));
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
}

const missing = [...used.keys()].filter((k) => !(k in catalog));
const unused = Object.keys(catalog).filter((k) => !used.has(k));

if (process.argv.includes('--json')) {
  console.log(JSON.stringify(Object.fromEntries(missing.map((k) => [k, ''])), null, 2));
} else {
  console.log(
    `${used.size} UI strings, ${used.size - missing.length} translated (${lang})`,
  );
  for (const k of missing)
    console.log(`  missing: ${JSON.stringify(k)}  (${used.get(k)})`);
  for (const k of unused) console.log(`  unused:  ${JSON.stringify(k)}`);
}
