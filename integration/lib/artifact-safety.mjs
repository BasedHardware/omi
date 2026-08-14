#!/usr/bin/env node
// LIFECYCLE: permanent
// Final retained-output guard. Runtime control records (readiness and process
// ownership) are inputs to the scan, never scan targets; every diagnostic and
// evidence artifact intended for retention must be secret/origin free.

import { lstatSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

function filesBelow(path) {
  const stat = lstatSync(path);
  if (stat.isFile()) return [path];
  if (!stat.isDirectory()) return [];
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = join(path, entry.name);
    return entry.isDirectory() ? filesBelow(child) : entry.isFile() ? [child] : [];
  });
}

export function retainedArtifactFailures({ paths, secrets = [] }) {
  const failures = [];
  for (const path of paths.flatMap(filesBelow)) {
    const content = readFileSync(path, "utf8");
    if (secrets.some((secret) => typeof secret === "string" && secret !== "" && content.includes(secret))) {
      failures.push(`${path}: contains the readiness credential`);
    }
    if (/https?:\/\//u.test(content)) failures.push(`${path}: contains an unsanitized base URL`);
    if (/authorization:\s*bearer\s+(?!\[redacted\](?:\s|$))[^\s]+/iu.test(content)) {
      failures.push(`${path}: contains an Authorization bearer credential`);
    }
    if (/\bOMI_API_TOKEN\s*=\s*(?!\[redacted\](?:\s|$))[^\s]+/u.test(content)) {
      failures.push(`${path}: contains an API token assignment`);
    }
  }
  return Object.freeze(failures);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const argv = process.argv.slice(2);
  const readinessIndex = argv.indexOf("--readiness");
  const readinessPath = readinessIndex === -1 ? null : argv[readinessIndex + 1];
  const paths = argv.flatMap((value, index) => value === "--path" && argv[index + 1] ? [argv[index + 1]] : []);
  try {
    if (!readinessPath || paths.length === 0) throw new Error("usage: artifact-safety.mjs --readiness <record> --path <retained-path>...");
    const readiness = JSON.parse(readFileSync(readinessPath, "utf8"));
    const failures = retainedArtifactFailures({ paths, secrets: [readiness.devToken] });
    if (failures.length > 0) throw new Error(failures.join("; "));
    process.stdout.write(`${JSON.stringify({ ok: true, files: paths.flatMap(filesBelow).length })}\n`);
  } catch (error) {
    process.stderr.write(`ERROR: ${error.message}\n`);
    process.exitCode = 1;
  }
}
