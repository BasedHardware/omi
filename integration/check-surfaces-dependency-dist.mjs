// LIFECYCLE: permanent
// Check only the workspace build outputs that the surfaces package resolves
// through. Runtime JS and declarations must exactly match a fresh in-memory
// TypeScript emit; build-mode metadata is checked independently with tsc --dry.

import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const coreRoot = resolve(here, "..", "core");
const surfacesName = "@omi-core/surfaces";

function listDependencyRows(prepareBuild) {
  const listArgs = prepareBuild
    ? ["-r", "list", "--depth", "-1", "--json"]
    : ["--filter", `${surfacesName}^...`, "list", "--depth", "-1", "--json"];
  return JSON.parse(
    execFileSync(
      "pnpm",
      listArgs,
      { cwd: coreRoot, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    ),
  );
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

function collectRuntimeTargets(value, targets = new Set(), isTypesBranch = false) {
  if (typeof value === "string") {
    if (!isTypesBranch) targets.add(value);
    return targets;
  }
  if (!value || typeof value !== "object") return targets;
  for (const [key, child] of Object.entries(value)) {
    collectRuntimeTargets(child, targets, isTypesBranch || key === "types");
  }
  return targets;
}

function isComparedEmit(path) {
  return /(?:\.[cm]?js|\.d\.[cm]?ts)$/.test(path);
}

function withoutTerminalLineFeed(content) {
  // `tsc -b`'s filesystem host appends one LF that Program.emit's callback
  // omits. It is runtime-neutral; all other emitted bytes must match.
  return content.endsWith("\n") ? content.slice(0, -1) : content;
}

function hashTree(hash, root, include) {
  if (!existsSync(root)) {
    hash.update(`missing\0${root}\0`);
    return;
  }
  for (const entry of readdirSync(root, { withFileTypes: true }).sort((left, right) => left.name.localeCompare(right.name))) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) hashTree(hash, path, include);
    else if (entry.isFile() && include(path)) {
      hash.update(`${path}\0${statSync(path).size}\0`);
      hash.update(readFileSync(path));
      hash.update("\0");
    }
  }
}

/** Exact-byte snapshot used by the render harness to avoid recompiling an
 * unchanged dependency graph while still rechecking before every import. */
export function dependencyDistFingerprint() {
  const hash = createHash("sha256");
  const rows = listDependencyRows(false);
  const fixedFiles = [
    join(coreRoot, "package.json"),
    join(coreRoot, "pnpm-lock.yaml"),
    join(coreRoot, "pnpm-workspace.yaml"),
    join(coreRoot, "tsconfig.base.json"),
    join(coreRoot, "packages", "surfaces", "package.json"),
  ];
  for (const path of fixedFiles) {
    hash.update(`${path}\0`);
    hash.update(existsSync(path) ? readFileSync(path) : "missing");
    hash.update("\0");
  }
  for (const row of rows.sort((left, right) => left.path.localeCompare(right.path))) {
    for (const name of ["package.json", "tsconfig.json", "tsconfig.base.json", "tsconfig.tsbuildinfo"]) {
      const path = join(row.path, name);
      hash.update(`${path}\0`);
      hash.update(existsSync(path) ? readFileSync(path) : "missing");
      hash.update("\0");
    }
    hashTree(hash, join(row.path, "src"), () => true);
    hashTree(hash, join(row.path, "dist"), isComparedEmit);
  }
  return hash.digest("hex");
}

/**
 * Compare compiler output with the files a runtime/type consumer will load.
 * Exported so the regression test can exercise the exact refusal seam without
 * mutating this checkout's shared build artifacts while other tests run.
 */
export function emittedOutputMismatches(packageName, packagePath, emittedOutputs) {
  const mismatches = [];
  for (const [outputPath, expected] of emittedOutputs) {
    if (!isComparedEmit(outputPath)) continue;
    const displayPath = relative(packagePath, outputPath);
    if (!existsSync(outputPath)) {
      mismatches.push(`missing compiler output — ${packageName}: ${displayPath}`);
    } else if (
      withoutTerminalLineFeed(readFileSync(outputPath, "utf8"))
      !== withoutTerminalLineFeed(expected)
    ) {
      mismatches.push(`stale compiler output — ${packageName}: ${displayPath} differs from current TypeScript emit`);
    }
  }
  return mismatches;
}

function emitProject(typescript, packageName, packagePath) {
  const configPath = join(packagePath, "tsconfig.json");
  const loaded = typescript.readConfigFile(configPath, typescript.sys.readFile);
  if (loaded.error) {
    return { errors: [`could not read ${packageName}'s tsconfig.json`], outputs: new Map() };
  }
  const parsed = typescript.parseJsonConfigFileContent(
    loaded.config,
    typescript.sys,
    packagePath,
    { composite: false, incremental: false, tsBuildInfoFile: undefined },
    configPath,
  );
  if (parsed.errors.length > 0) {
    return { errors: [`could not parse ${packageName}'s tsconfig.json`], outputs: new Map() };
  }

  const outputs = new Map();
  const program = typescript.createProgram({
    rootNames: parsed.fileNames,
    options: parsed.options,
    projectReferences: parsed.projectReferences,
  });
  const result = program.emit(undefined, (outputPath, content) => {
    outputs.set(resolve(outputPath), content);
  });
  return {
    errors: result.emitSkipped ? [`fresh TypeScript emit was skipped for ${packageName}`] : [],
    outputs,
  };
}

export function runDependencyDistCheck({ prepareBuild = false } = {}) {
  let failed = false;
  const fail = (message) => {
    console.error(`  BROKEN dist:surface-deps      ${message}`);
    failed = true;
  };

  let dependencyRows;
  try {
    dependencyRows = listDependencyRows(prepareBuild);
  } catch (error) {
    fail(
      prepareBuild
        ? "could not ask pnpm for the core workspace package list"
        : `could not ask pnpm for ${surfacesName}'s workspace dependencies`,
    );
    if (error.stderr) console.error(String(error.stderr).trim());
    return 1;
  }

  const missingOutputs = [];
  const missingOutputPackages = new Set();
  const buildModeProjects = [];
  const compilerProjects = [];
  const presenceOnly = [];
  let declaredTypeOutputCount = 0;
  let declaredRuntimeOutputCount = 0;

  for (const row of dependencyRows) {
    const manifestPath = join(row.path, "package.json");
    const manifest = readJson(manifestPath);
    const typeTargets = collectTypeTargets(manifest.exports);
    if (typeof manifest.types === "string") typeTargets.add(manifest.types);
    const runtimeTargets = collectRuntimeTargets(manifest.exports);
    if (typeof manifest.main === "string") runtimeTargets.add(manifest.main);
    if (typeof manifest.module === "string") runtimeTargets.add(manifest.module);

    for (const [kind, targets] of [["type", typeTargets], ["runtime", runtimeTargets]]) {
      for (const target of targets) {
        if (kind === "type") declaredTypeOutputCount += 1;
        else declaredRuntimeOutputCount += 1;
        const outputPath = resolve(row.path, target);
        if (!existsSync(outputPath)) {
          missingOutputs.push(`${manifest.name}: ${relative(row.path, outputPath)}`);
          missingOutputPackages.add(manifest.name);
        }
      }
    }

    const buildScript = manifest.scripts?.build ?? "";
    if (/^tsc\s+-b(?:\s|$)/.test(buildScript)) {
      buildModeProjects.push(join(row.path, "tsconfig.json"));
    }
    if (/(?:^|&&\s*)tsc(?:\s|$)/.test(buildScript) && existsSync(join(row.path, "tsconfig.json"))) {
      compilerProjects.push({ name: manifest.name, path: row.path });
    } else {
      presenceOnly.push(manifest.name);
    }
  }

  if (prepareBuild) {
    // `tsc -b` trusts tsconfig.tsbuildinfo when an output was deleted. Invalidate
    // only that package's ignored build cache so its normal build repairs it.
    for (const row of dependencyRows) {
      const manifest = readJson(join(row.path, "package.json"));
      if (
        missingOutputPackages.has(manifest.name)
        && /^tsc\s+-b(?:\s|$)/.test(manifest.scripts?.build ?? "")
      ) {
        rmSync(join(row.path, "tsconfig.tsbuildinfo"), { force: true });
        console.log(`invalidated missing-output build cache: ${manifest.name}`);
      }
    }
    return 0;
  }

  for (const missing of missingOutputs) fail(`missing declared output — ${missing}`);

  const tsc = join(coreRoot, "packages", "surfaces", "node_modules", ".bin", "tsc");
  if (!existsSync(tsc)) {
    fail("cannot run TypeScript checks because surfaces/node_modules/.bin/tsc is missing");
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

  if (existsSync(tsc)) {
    try {
      const require = createRequire(join(coreRoot, "packages", "surfaces", "package.json"));
      const typescript = require("typescript");
      for (const project of compilerProjects) {
        const emitted = emitProject(typescript, project.name, project.path);
        for (const error of emitted.errors) fail(error);
        for (const mismatch of emittedOutputMismatches(project.name, project.path, emitted.outputs)) {
          fail(mismatch);
        }
      }
    } catch (error) {
      fail(`could not create a fresh TypeScript emit: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (failed) {
    console.error(`         → cd ${coreRoot} && pnpm --filter ${surfacesName}... build`);
  } else {
    console.log(
      `  ok     dist:surface-deps      ${declaredRuntimeOutputCount} runtime and `
      + `${declaredTypeOutputCount} type targets present; fresh compiler emit matches `
      + `${compilerProjects.length} dependency projects; tsc --build --dry says `
      + `${buildModeProjects.length} build-mode projects are current`,
    );
  }

  if (presenceOnly.length > 0) {
    console.log(
      `  note   dist:surface-deps      declared output presence only (not freshness): ${presenceOnly.join(", ")}`,
    );
  }
  return failed ? 1 : 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = runDependencyDistCheck({ prepareBuild: process.argv.includes("--prepare-build") });
}
