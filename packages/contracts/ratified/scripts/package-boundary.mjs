import { createHash } from "node:crypto";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { forbiddenProjectionFields, forbiddenTraceFields } from "../fixtures/forbidden-public-fields.mjs";

const root = resolve(import.meta.dirname, "..");
const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8"));
const provenanceBytes = readFileSync(resolve(root, "PROVENANCE.json"));
const provenance = JSON.parse(provenanceBytes);

/**
 * COORD-contract-evolution-policy.md §1: "The version number is an
 * identifier. The compatibility class is the contract" - checked mechanically,
 * declared explicitly in ARTIFACT.json rather than inferred from semver.
 * Exactly two values exist; there is no third.
 *
 * 0.3.0 added the write wire and was `additive`: one new export subpath
 * (`./write/ops`) and two fixture corpora, removing and narrowing nothing.
 *
 * 0.4.0 was `breaking`: it retracted `WRITE_ERRORS.maintenance.body` to `null`
 * because the 503 body was under escalation to fable and a ratified contract
 * must not fix a byte string a pending ruling may move.
 *
 * 0.5.0 is `breaking`. Fable ruled (COORD-fable-rulings-wave2 W1) and the body
 * is now ratified — but `WRITE_ERRORS.maintenance` is REMOVED rather than
 * refilled, and the value lands in a new `WRITE_AVAILABILITY` table with its own
 * reader. Removing anything is `breaking` by §1's rules, and the removal is the
 * point: the ruling's binding condition is that the fifth value is an
 * AVAILABILITY SIGNAL, not a fifth authorization outcome, and leaving it beside
 * the request-errors would have encoded in code the framing the ruling refused.
 *
 * §8's breaking-bump discipline, satisfied rather than waved:
 *   - WHAT DATA WRITTEN UNDER 0.5.0 MEANS TO A CLIENT ON 0.4.0: nothing. This is
 *     a REQUEST-shape and outcome-table contract; no data is persisted in any
 *     shape it defines.
 *   - IS IT IRREVERSIBLE? No. 0.4.0 is adopted only on the platform trunk, with
 *     no client in the field, so rollback is a re-vendor.
 *
 * 0.6.0 is `additive`. It adds ONE new export subpath (`./projections/tasks`)
 * and two fixture files, and changes no existing export, field, shape or
 * validator. Every client built against 0.5.0 keeps working unchanged with no
 * new obligation, which is §1's definition.
 *
 * The precedent is exact rather than argued: 0.3.0 added `./write/ops` — a
 * subpath whose own shapes carry REQUIRED fields — and was classified
 * `additive` for this same reason. §1's "adding a required field is breaking"
 * governs a field added to an EXISTING shape; a new namespace imposes nothing
 * on a client that never imports it. The tasks item's thirteen fields are all
 * required inside a shape no prior version had.
 */
const COMPATIBILITY_CLASS = "additive";
if (COMPATIBILITY_CLASS !== "additive" && COMPATIBILITY_CLASS !== "breaking") {
  throw new Error("compatibility class must be exactly 'additive' or 'breaking'");
}

const expectedExports = ["./pagination/cursor", "./projections/synthesized", "./projections/tasks", "./recall/trace", "./write/ops"];
const expectedManifestFiles = [
  "dist/pagination/cursor.js",
  "dist/pagination/cursor.d.ts",
  "dist/projections/synthesized.js",
  "dist/projections/synthesized.d.ts",
  "dist/projections/tasks.js",
  "dist/projections/tasks.d.ts",
  "dist/recall/trace.js",
  "dist/recall/trace.d.ts",
  "dist/wire/json.js",
  "dist/wire/json.d.ts",
  "dist/write/ops.js",
  "dist/write/ops.d.ts",
  "fixtures/manifest.json",
  "fixtures/read-page-windows.json",
  "fixtures/recall-completeness.json",
  "fixtures/recall-trace.json",
  "fixtures/page-conformance.json",
  "fixtures/status-matrix.json",
  "fixtures/write-ops-outcomes.json",
  "fixtures/write-ops-conformance.json",
  "fixtures/tasks-read-shape.json",
  "fixtures/tasks-read-conformance.json",
  "PROVENANCE.json",
];
const expectedTarFiles = [
  "package/PROVENANCE.json",
  "package/README.md",
  "package/dist/pagination/cursor.d.ts",
  "package/dist/pagination/cursor.js",
  "package/dist/projections/synthesized.d.ts",
  "package/dist/projections/synthesized.js",
  "package/dist/projections/tasks.d.ts",
  "package/dist/projections/tasks.js",
  "package/dist/recall/trace.d.ts",
  "package/dist/recall/trace.js",
  "package/dist/wire/json.d.ts",
  "package/dist/wire/json.js",
  "package/dist/write/ops.d.ts",
  "package/dist/write/ops.js",
  "package/fixtures/manifest.json",
  "package/fixtures/read-page-windows.json",
  "package/fixtures/recall-completeness.json",
  "package/fixtures/recall-trace.json",
  "package/fixtures/page-conformance.json",
  "package/fixtures/status-matrix.json",
  "package/fixtures/tasks-read-conformance.json",
  "package/fixtures/tasks-read-shape.json",
  "package/fixtures/write-ops-conformance.json",
  "package/fixtures/write-ops-outcomes.json",
  "package/package.json",
].sort();

assertEqual(Object.keys(manifest.exports).sort(), expectedExports, "export allowlist");
assertEqual(manifest.files, expectedManifestFiles, "manifest file allowlist");
if (manifest.name !== "@omi-core/ratified-contracts" || manifest.version !== "0.6.0" || manifest.private !== true) throw new Error("package identity/version/private status drifted");
if (provenance.package.name !== manifest.name || provenance.package.version !== manifest.version) throw new Error("package provenance identity mismatch");

const declaration = readFileSync(resolve(root, "dist/projections/synthesized.d.ts"), "utf8");
// domain-pending(DIV-DOMCORE-003)
if (/export (?:interface|type) Memory\b/.test(declaration)) throw new Error("legacy editable Memory escaped the package");
// domain-pending(DIV-DOMCORE-005)
if (/\bConversationMemory\b|FEAT-CONV-012/.test(declaration)) throw new Error("open conversation-memory surface escaped the package");
if (/\bid:\s*RecordId\b/.test(declaration)) throw new Error("synthesized render id incorrectly reuses RecordId");
for (const forbiddenField of forbiddenProjectionFields) {
  if (new RegExp(`\\b${forbiddenField}\\??:`).test(declaration)) throw new Error(`forbidden legacy/presentational field escaped: ${forbiddenField}`);
}
for (const requiredField of [
  "id", "text", "citations", "provenance", "synthesisVersion", "inputDigest", "outputDigest",
  "declaredFrontier", "newestSearchedAcceptedFrontier", "missingAcceptedFrontierReason",
  // domain-pending(DIV-DOMCORE-006)
  "newestSearchedStmFrontier", "missingStmFrontierReason",
]) {
  if (!new RegExp(`\\b${requiredField}\\??:`).test(declaration)) throw new Error(`frozen ready-item field missing: ${requiredField}`);
}
if (/\b(?:EmptyItem|FailedItem|ReadyItem)\b/.test(declaration)) throw new Error("non-ready item state escaped the projection");

/**
 * D2's parity, checked against the DOMAIN CONTRACT rather than against a list
 * someone retyped here.
 *
 * `DAVID-tasks-read-epoch-and-ci` D2 ratifies "everything
 * core/contracts/src/domain/tasks.ts already declares", and says why: parity is
 * what makes the flip mechanical, because a narrower surface renders
 * differently and turns a factory-line change into a product event. A hardcoded
 * list of thirteen names here would go stale the day the domain gains a
 * fourteenth field and would report parity while the wire had quietly narrowed.
 *
 * So the domain's `Task` interface is the source and this reads it. The file
 * sits outside the package (`../../src/domain/tasks.ts`), which is why it is
 * checked HERE and not in the packed fixtures: the tarball is standalone by
 * design, and reaching out of it at consumer runtime would be the defect. The
 * boundary script always runs in the source checkout.
 */
const taskDeclaration = readFileSync(resolve(root, "dist/projections/tasks.d.ts"), "utf8");
/**
 * COMMENTS ARE STRIPPED BEFORE THE `RecordId` BAN, and the first draft of this
 * check proved why in about four seconds: the module header EXPLAINS that the
 * id is never a `RecordId`, `tsc` emits doc comments into the `.d.ts`, and the
 * check failed on its own rationale. That is this repo's already-shipped
 * failure — a fence that banned an ordinary word and fired on prose while
 * catching no real reference (`swarm-protocol.md` §8) — reproduced verbatim.
 * Prose cannot type anything.
 */
const taskDeclarationCode = taskDeclaration
  .replace(/\/\*[\s\S]*?\*\//g, (match) => match.replace(/[^\n]/g, " "))
  .replace(/\/\/[^\n]*/g, "");
if (/\bid:\s*RecordId\b/.test(taskDeclarationCode)) throw new Error("tasks item id incorrectly reuses RecordId — D2 requires the opaque ref");
if (/\bRecordId\b/.test(taskDeclarationCode)) throw new Error("RecordId escaped into the tasks read wire");
const domainTaskSource = readFileSync(resolve(root, "../src/domain/tasks.ts"), "utf8");
const domainTaskBody = domainTaskSource.slice(
  domainTaskSource.indexOf("export interface Task {"),
  domainTaskSource.indexOf("\n}", domainTaskSource.indexOf("export interface Task {")),
);
if (!domainTaskBody.startsWith("export interface Task {")) throw new Error("could not locate the domain Task interface — the parity check is stale");
const domainTaskFields = [...domainTaskBody.matchAll(/^\s{2}(\w+)[?]?:/gm)].map((match) => match[1]).sort();
if (domainTaskFields.length !== 13) throw new Error(`domain Task declares ${domainTaskFields.length} fields, not the thirteen D2 ratifies — reconcile the wire before this bump lands`);
const wireTaskFields = [...taskDeclarationCode.matchAll(/^\s{8}(\w+):/gm)].map((match) => match[1]);
for (const field of domainTaskFields) {
  if (!wireTaskFields.includes(field)) throw new Error(`tasks read wire is missing domain field \`${field}\` — D2 requires full parity`);
}

const traceDeclaration = readFileSync(resolve(root, "dist/recall/trace.d.ts"), "utf8");
for (const forbiddenField of forbiddenTraceFields) {
  if (new RegExp(`\\b${forbiddenField}\\??:`).test(traceDeclaration)) throw new Error(`content-bearing trace field escaped: ${forbiddenField}`);
}

const scratch = mkdtempSync(resolve(tmpdir(), "omi-contract-package-"));
try {
  const packDirectory = resolve(scratch, "pack");
  run("mkdir", ["-p", packDirectory], scratch);
  const pack = run("npm", ["pack", "--json", "--ignore-scripts", "--pack-destination", packDirectory], root);
  const packResult = JSON.parse(pack);
  if (!Array.isArray(packResult) || packResult.length !== 1) throw new Error("expected one packed artifact");
  const tarball = resolve(packDirectory, packResult[0].filename);
  const tarFiles = run("tar", ["-tzf", tarball], scratch).trim().split("\n").sort();
  assertEqual(tarFiles, expectedTarFiles, "packed file allowlist");

  const artifact = {
    schemaVersion: 1,
    package: { name: manifest.name, version: manifest.version },
    compatibility: COMPATIBILITY_CLASS,
    provenanceSha256: sha256(provenanceBytes),
    sourceDigest: provenance.sourceDigest,
    tarballSha256: sha256(readFileSync(tarball)),
    files: expectedTarFiles,
  };
  const artifactRendered = `${JSON.stringify(artifact, null, 2)}\n`;
  const artifactPath = resolve(root, "ARTIFACT.json");
  if (process.argv.includes("--write")) {
    writeFileSync(artifactPath, artifactRendered);
  } else if (process.argv.includes("--check")) {
    if (readFileSync(artifactPath, "utf8") !== artifactRendered) throw new Error("ARTIFACT.json drifted; review package and run package-boundary.mjs --write");
  } else {
    throw new Error("use --check or --write");
  }

  const consumer = resolve(scratch, "consumer");
  run("mkdir", ["-p", consumer], scratch);
  cpSync(resolve(root, "fixtures/clean-consumer/consumer.ts"), resolve(consumer, "consumer.ts"));
  cpSync(resolve(root, "fixtures/clean-consumer/conformance.mjs"), resolve(consumer, "conformance.mjs"));
  writeFileSync(resolve(consumer, "package.json"), `${JSON.stringify({ private: true, type: "module", dependencies: { "@omi-core/ratified-contracts": `file:${tarball}` } }, null, 2)}\n`);
  writeFileSync(resolve(consumer, "tsconfig.json"), `${JSON.stringify({ compilerOptions: {
    target: "ES2023", module: "NodeNext", moduleResolution: "NodeNext", strict: true,
    noUncheckedIndexedAccess: true, exactOptionalPropertyTypes: true, isolatedModules: true,
    verbatimModuleSyntax: true, skipLibCheck: false, outDir: "dist"
  }, include: ["consumer.ts"] }, null, 2)}\n`);
  run("npm", ["install", "--offline", "--ignore-scripts", "--no-audit", "--no-fund"], consumer);
  run(resolve(root, "node_modules/.bin/tsc"), ["-p", "tsconfig.json"], consumer);
  const runtime = run("node", ["dist/consumer.js"], consumer);
  run("node", ["conformance.mjs"], consumer);
  runReject("node", ["--input-type=module", "--eval", "import('@omi-core/ratified-contracts')"], consumer, "package root must not resolve");
  runReject("node", ["--input-type=module", "--eval", "import('@omi-core/ratified-contracts/ids')"], consumer, "unlisted subpath must not resolve");

  console.log(JSON.stringify({
    package: artifact.package,
    sourceDigest: artifact.sourceDigest,
    provenanceSha256: artifact.provenanceSha256,
    tarballSha256: artifact.tarballSha256,
    files: artifact.files,
    cleanConsumer: "typecheck+runtime passed",
    runtime,
  }, null, 2));
} finally {
  rmSync(scratch, { recursive: true, force: true });
}

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, encoding: "utf8", env: { ...process.env, npm_config_cache: resolve(scratch ?? tmpdir(), "npm-cache") } });
  if (result.status !== 0) throw new Error(`${command} ${args.join(" ")} failed\n${result.stderr}${result.stdout}`);
  return result.stdout;
}

function runReject(command, args, cwd, label) {
  const result = spawnSync(command, args, { cwd, encoding: "utf8" });
  if (result.status === 0) throw new Error(`${label}: ${command} ${args.join(" ")} unexpectedly succeeded`);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function assertEqual(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`${label} drifted\nexpected=${JSON.stringify(expected)}\nactual=${JSON.stringify(actual)}`);
}
