import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const coreRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const surfacesName = "@omi-core/surfaces";

export function listSurfaceDependencyRows(prepareBuild = false) {
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

function isComparedEmit(path) {
  return /(?:\.[cm]?js|\.d\.[cm]?ts)$/.test(path);
}

function hashTree(hash, root, include) {
  if (!existsSync(root)) {
    hash.update(`missing\0${root}\0`);
    return;
  }
  const entries = readdirSync(root, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name));
  for (const entry of entries) {
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
  const rows = listSurfaceDependencyRows();
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
