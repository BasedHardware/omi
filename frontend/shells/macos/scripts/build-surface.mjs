#!/usr/bin/env node
// Production-shaped surface build: strip TS types to .js, rewrite ./x.ts imports
// to ./x.js, make asset paths relative so the output can be bundle-loaded.
// Usage: OMI_BUILD_DIR=<dir> node scripts/build-surface.mjs
import { readdirSync, mkdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, extname } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "surface");
const out = join(process.env.OMI_BUILD_DIR ?? join(root, ".build"), "surface");

const walk = (d) =>
  readdirSync(d).flatMap((n) => {
    const p = join(d, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });

let n = 0;
for (const file of walk(src)) {
  const rel = relative(src, file);
  if (rel === "devserver.mjs") continue;
  const ext = extname(file);
  let body = readFileSync(file, "utf8");
  let dest = join(out, rel);
  if (ext === ".ts") {
    body = stripTypeScriptTypes(body, { mode: "strip" }).replace(/(\.\/[\w.-]+)\.ts"/g, '$1.js"');
    dest = dest.replace(/\.ts$/, ".js");
  }
  if (ext === ".html") body = body.replace(/(src|href)="\/([^"]+?)(\.ts)?"/g, (_m, a, p) => `${a}="./${p}${p.endsWith(".css") ? "" : ".js"}"`);
  mkdirSync(dirname(dest), { recursive: true });
  writeFileSync(dest, body);
  n++;
}
console.log(`surface: ${n} file(s) -> ${relative(root, out)}`);
