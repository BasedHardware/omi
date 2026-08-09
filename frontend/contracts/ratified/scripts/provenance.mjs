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
  "src/projections/tasks.ts",
  "src/recall/trace.ts",
  "src/wire/json.ts",
  "src/write/ops.ts",
  "fixtures/clean-consumer/consumer.ts",
  "fixtures/clean-consumer/conformance.mjs",
  "fixtures/clean-consumer/tsconfig.json",
  "fixtures/forbidden-public-fields.mjs",
  "fixtures/read-page-windows.json",
  "fixtures/recall-completeness.json",
  "fixtures/recall-trace.json",
  "fixtures/page-conformance.json",
  "fixtures/status-matrix.json",
  "fixtures/write-ops-outcomes.json",
  "fixtures/write-ops-conformance.json",
  "fixtures/tasks-read-shape.json",
  "fixtures/tasks-read-conformance.json",
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
  // COORD-prefixed ids are cross-cutting decisions in data/*/decisions/, cited
  // by document slug. That grammar was an open question at the 0.2.0 bump and
  // is now settled: COORD-contract-evolution-policy's "First exercise" section
  // fixes it ("a cross-cutting ruling is cited by its document slug, prefixed
  // COORD-"), so the slug below is the defined form, not a best guess.
  //
  // 0.6.0 adds "DAVID-tasks-read-epoch-and-ci" — D1 (the tasks read wire mirrors
  // the memories read model: reader-scoped opaque ids, cursor pagination, a
  // completeness envelope) and D2 (full thirteen-field parity), signed by David
  // in person. It is cited by its document slug, which is the grammar the
  // policy's "First exercise" section fixes; the COORD- prefix in the ids above
  // is those documents' own filename prefix, not a required namespace, and
  // stamping COORD- onto a David-signed record would misattribute who signed it.
  //
  // 0.5.0 adds "COORD-fable-rulings-wave2" — W1, which SIGNS the fifth wire
  // value `control_unavailable` AND binds how this contract must record it: as
  // an availability signal, never as a fifth authorization outcome.
  //
  // 0.4.0 added "COORD-cross-generation-writes" — the ratified ruling that
  // governs migration windows and straggler disposition, and therefore the one
  // that governs the 503/backpressure semantics 0.4.0 declines to fix bytes for.
  //
  // 0.3.0 added "COORD-write-path-rulings" — the RATIFIED write-path rulings
  // (B1 minted write_id, B2 stale_epoch as its own refusal outcome, B4
  // POST /v1/{domain}/ops, B6 tasks-first but domain-generic). Per the
  // evolution policy §3 a bump is valid only if this array gains a ratified
  // ruling id the previous version did not carry; that is what this line is.
  rulings: ["ADR-004", "ADR-008", "WS-006", "M-001", "DIV-MEM-004", "FEAT-MEM-001", "FEAT-MEM-002", "FC-AUTH-003", "FEAT-AUTH-011", "COORD-contract-evolution-policy", "COORD-write-path-rulings", "COORD-cross-generation-writes", "COORD-fable-rulings-wave2", "DAVID-tasks-read-epoch-and-ci"],
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
