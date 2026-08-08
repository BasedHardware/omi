import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { relative, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const packageRoot = root;
const inputs = [
  "package.json",
  "tsconfig.json",
  "README.md",
  "src/pagination/cursor.ts",
  "src/projections/synthesized.ts",
  "src/recall/trace.ts",
  "fixtures/clean-consumer/consumer.ts",
  "fixtures/clean-consumer/conformance.mjs",
  "fixtures/clean-consumer/tsconfig.json",
  "fixtures/forbidden-public-fields.mjs",
  "fixtures/read-page-windows.json",
  "fixtures/recall-completeness.json",
  "fixtures/recall-trace.json",
  "fixtures/page-conformance.json",
  "fixtures/status-matrix.json",
  "fixtures/manifest.json",
  "test/contracts.test.mjs",
  "scripts/check-domain-markers.mjs",
  "scripts/clean.mjs",
  "scripts/provenance.mjs",
  "scripts/package-boundary.mjs",
  "scripts/verify-ci.mjs",
  "tsconfig.base.json",
  "pnpm-lock.yaml"
].map((path) => resolve(root, path));

const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
const entries = inputs.map((path) => {
  const content = readFileSync(path);
  return {
    path: relative(packageRoot, path).replaceAll("\\", "/"),
    sha256: createHash("sha256").update(content).digest("hex"),
    bytes: content.byteLength,
  };
}).sort((left, right) => left.path.localeCompare(right.path));
const sourceDigest = createHash("sha256").update(JSON.stringify(entries)).digest("hex");
const provenance = {
  schemaVersion: 1,
  package: { name: manifest.name, version: manifest.version },
  repository: "BasedHardware/omi",
  baselineCommit: "e5deec43d8814191b90d3e3db46e99bec29ae724",
  rulings: ["ADR-004", "WS-006", "M-001", "DIV-MEM-004", "FEAT-MEM-001", "FEAT-MEM-002", "FC-AUTH-003", "FEAT-AUTH-011"],
  compiler: { name: "typescript", version: manifest.devDependencies.typescript },
  inputs: entries,
  sourceDigest,
};
const rendered = `${JSON.stringify(provenance, null, 2)}\n`;
const target = resolve(root, "PROVENANCE.json");

if (process.argv.includes("--write")) {
  writeFileSync(target, rendered);
  console.log(`wrote ${relative(packageRoot, target)} ${sourceDigest}`);
} else if (process.argv.includes("--check")) {
  if (readFileSync(target, "utf8") !== rendered) throw new Error("PROVENANCE.json drifted; review inputs and run provenance.mjs --write");
  console.log(`provenance OK: ${sourceDigest}`);
} else {
  throw new Error("use --check or --write");
}
