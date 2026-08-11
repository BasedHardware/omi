#!/usr/bin/env node
// LIFECYCLE: permanent
// Persist only diagnostic shape, never credentials or backend origins.

import { readFileSync, writeFileSync } from "node:fs";

const argv = process.argv.slice(2);
const flag = (name) => {
  const index = argv.indexOf(name);
  return index === -1 ? null : argv[index + 1];
};
const input = flag("--in");
const output = flag("--out");
if (!input || !output) {
  process.stderr.write("usage: sanitize-log.mjs --in <raw> --out <safe> [--redact <value>]...\n");
  process.exit(2);
}
const redactions = argv.flatMap((value, index) => value === "--redact" && argv[index + 1] ? [argv[index + 1]] : []);
let text = readFileSync(input, "utf8");
for (const value of redactions.filter(Boolean)) text = text.split(value).join("[redacted]");
text = text
  .replace(/https?:\/\/[^\s)'"]+/gu, "[redacted-origin]")
  .replace(/(authorization:\s*bearer\s+)[^\s]+/giu, "$1[redacted]");
writeFileSync(output, text);
