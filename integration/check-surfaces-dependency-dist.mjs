// LIFECYCLE: permanent
// Check only the workspace build outputs that the surfaces package resolves
// through. This deliberately does not call itself a general dist-freshness
// check: TypeScript build-mode projects get the compiler's own dry-run verdict;
// non-build-mode packages get presence checks for manifest-declared type files.

import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const coreRoot = resolve(here, "..", "core");
const surfacesName = "@omi-core/surfaces";
const prepareBuild = process.argv.includes("--prepare-build");

function fail(message) {
  console.error(`  BROKEN dist:surface-deps      ${message}`);
  process.exitCode = 1;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function collectTypeTargets(value, targets = new Set()) {
  if (!value || typeof value !== "object") return targets;
  for (const [key, child] of Object.entries(value)) {
    if (key === "types" && typeof child === "string") targets.add(child);
    else collectTypeTargets(child, targets);
  }
  return targets;
}

let dependencyRows;
try {
  const listArgs = prepareBuild
    ? ["-r", "list", "--depth", "-1", "--json"]
    : ["--filter", `${surfacesName}^...`, "list", "--depth", "-1", "--json"];
  dependencyRows = JSON.parse(
    execFileSync(
      "pnpm",
      listArgs,
      { cwd: coreRoot, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    ),
  );
} catch (error) {
  fail(
    prepareBuild
      ? "could not ask pnpm for the core workspace package list"
      : `could not ask pnpm for ${surfacesName}'s workspace dependencies`,
  );
  if (error.stderr) console.error(String(error.stderr).trim());
  process.exit();
}

const missingOutputs = [];
const missingOutputPackages = new Set();
const buildModeProjects = [];
const presenceOnly = [];
let declaredOutputCount = 0;

for (const row of dependencyRows) {
  const manifestPath = join(row.path, "package.json");
  const manifest = readJson(manifestPath);
  const typeTargets = collectTypeTargets(manifest.exports);
  if (typeof manifest.types === "string") typeTargets.add(manifest.types);

  for (const target of typeTargets) {
    declaredOutputCount += 1;
    const outputPath = resolve(row.path, target);
    if (!existsSync(outputPath)) {
      missingOutputs.push(`${manifest.name}: ${relative(row.path, outputPath)}`);
      missingOutputPackages.add(manifest.name);
    }
  }

  if (/^tsc\s+-b(?:\s|$)/.test(manifest.scripts?.build ?? "")) {
    buildModeProjects.push(join(row.path, "tsconfig.json"));
  } else {
    presenceOnly.push(manifest.name);
  }
}

if (prepareBuild) {
  // `tsc -b` trusts tsconfig.tsbuildinfo even when a declaration output was
  // deleted: it exits 0, says Done, and emits nothing. Invalidate only that
  // package's ignored build cache; its normal build script then does the repair.
  for (const row of dependencyRows) {
    const manifest = readJson(join(row.path, "package.json"));
    if (
      missingOutputPackages.has(manifest.name) &&
      /^tsc\s+-b(?:\s|$)/.test(manifest.scripts?.build ?? "")
    ) {
      rmSync(join(row.path, "tsconfig.tsbuildinfo"), { force: true });
      console.log(`invalidated missing-output build cache: ${manifest.name}`);
    }
  }
  process.exit(0);
}

for (const missing of missingOutputs) fail(`missing declared type output — ${missing}`);

const tsc = join(coreRoot, "packages", "surfaces", "node_modules", ".bin", "tsc");
if (!existsSync(tsc)) {
  fail("cannot run TypeScript's build dry-run because surfaces/node_modules/.bin/tsc is missing");
} else if (buildModeProjects.length > 0) {
  const dryRun = spawnSync(tsc, ["-b", ...buildModeProjects, "--dry", "--verbose"], {
    cwd: coreRoot,
    encoding: "utf8",
  });
  const output = `${dryRun.stdout ?? ""}\n${dryRun.stderr ?? ""}`;
  const staleReasons = output
    .split(/\r?\n/)
    .map((line) => line.replace(/^.*? - /, "").trim())
    .filter((line) => line.includes(" is out of date because "));

  if (dryRun.status !== 0) {
    fail(`TypeScript build dry-run failed with exit ${dryRun.status}`);
    const detail = output.trim();
    if (detail) console.error(detail);
  } else {
    for (const reason of staleReasons) fail(reason);
  }
}

if (process.exitCode) {
  console.error(
    `         → cd ${coreRoot} && pnpm --filter ${surfacesName}... build`,
  );
} else {
  console.log(
    `  ok     dist:surface-deps      ${declaredOutputCount} declared type outputs present; ` +
      `tsc --build --dry says ${buildModeProjects.length} dependency projects are current`,
  );
}

if (presenceOnly.length > 0) {
  console.log(
    `  note   dist:surface-deps      output presence only (not freshness): ${presenceOnly.join(", ")}`,
  );
}
