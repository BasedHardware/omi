import {
  lstatSync,
  readFileSync,
  readdirSync,
  realpathSync,
} from "node:fs";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";

const MAX_MANIFEST_BYTES = 1024 * 1024;
const MAX_PACKAGES = 10_000;
const REQUIRED = new Map([
  ["firebase-admin", "14.2.0"],
  ["hono", "4.12.34"],
]);
const FORBIDDEN = new Set([
  "@google-cloud/firestore",
  "@google-cloud/storage",
  "uuid",
]);
const FORBIDDEN_IMPORTS = [
  "@google-cloud/firestore",
  "@google-cloud/storage",
  "firebase-admin/firestore",
  "firebase-admin/storage",
];
const SOURCE_ROOTS = ["apps", "core", "drivers"];
const SOURCE_SUFFIXES = [".cjs", ".js", ".mjs", ".ts", ".tsx"];

export class ClosureVerificationError extends Error {
  constructor(code) {
    super(code);
    this.name = "ClosureVerificationError";
    this.code = code;
  }
}

function fail(code) {
  throw new ClosureVerificationError(code);
}

function entries(directory) {
  try {
    return readdirSync(directory, { withFileTypes: true });
  } catch {
    fail("dependency_tree_unreadable");
  }
}

function canonicalInside(root, candidate) {
  let canonical;
  try {
    canonical = realpathSync(candidate);
  } catch {
    fail("package_link_unresolvable");
  }
  const rel = relative(root, canonical);
  if (rel === "" || rel === ".." || rel.startsWith(`..${sep}`) || isAbsolute(rel)) {
    fail("package_link_outside_root");
  }
  return canonical;
}

function packageManifest(packageDirectory) {
  const path = join(packageDirectory, "package.json");
  let bytes;
  try {
    bytes = readFileSync(path);
  } catch {
    fail("package_manifest_missing");
  }
  if (bytes.byteLength === 0 || bytes.byteLength > MAX_MANIFEST_BYTES) {
    fail("package_manifest_size_invalid");
  }
  let parsed;
  try {
    parsed = JSON.parse(bytes.toString("utf8"));
  } catch {
    fail("package_manifest_malformed");
  }
  if (
    parsed === null ||
    Array.isArray(parsed) ||
    typeof parsed !== "object" ||
    typeof parsed.name !== "string" ||
    parsed.name.length === 0 ||
    parsed.name.length > 214 ||
    typeof parsed.version !== "string" ||
    !/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(parsed.version)
  ) {
    fail("package_manifest_shape_invalid");
  }
  return { name: parsed.name, version: parsed.version };
}

function directPackageDirectories(moduleRoot) {
  const result = [];
  for (const entry of entries(moduleRoot)) {
    if (entry.name === ".bin" || entry.name === ".cache") continue;
    const path = join(moduleRoot, entry.name);
    if (entry.name === ".bun") {
      for (const storeEntry of entries(path)) {
        if (!storeEntry.isDirectory()) continue;
        const nestedModules = join(path, storeEntry.name, "node_modules");
        try {
          const nestedStat = lstatSync(nestedModules);
          if (nestedStat.isDirectory() || nestedStat.isSymbolicLink()) {
            result.push({ moduleRoot: nestedModules });
          }
        } catch {
          // Store metadata entries without node_modules are not packages.
        }
      }
      continue;
    }
    if (entry.name.startsWith("@") && entry.isDirectory()) {
      for (const scopedEntry of entries(path)) {
        result.push({ packageDirectory: join(path, scopedEntry.name) });
      }
      continue;
    }
    result.push({ packageDirectory: path });
  }
  return result;
}

function installedPackages(root) {
  let canonicalRoot;
  try {
    canonicalRoot = realpathSync(resolve(root));
  } catch {
    fail("artifact_root_unreadable");
  }
  const queue = [join(canonicalRoot, "node_modules")];
  const seenModuleRoots = new Set();
  const seenPackages = new Set();
  const packages = [];

  while (queue.length > 0) {
    const moduleRoot = queue.shift();
    const canonicalModuleRoot = canonicalInside(canonicalRoot, moduleRoot);
    if (seenModuleRoots.has(canonicalModuleRoot)) continue;
    seenModuleRoots.add(canonicalModuleRoot);

    for (const item of directPackageDirectories(canonicalModuleRoot)) {
      if (item.moduleRoot) {
        queue.push(item.moduleRoot);
        continue;
      }
      const canonicalPackage = canonicalInside(canonicalRoot, item.packageDirectory);
      if (seenPackages.has(canonicalPackage)) continue;
      seenPackages.add(canonicalPackage);
      const manifest = packageManifest(canonicalPackage);
      packages.push({ ...manifest, canonicalPackage });
      if (packages.length > MAX_PACKAGES) fail("package_count_exceeded");
      try {
        const nestedStat = lstatSync(join(canonicalPackage, "node_modules"));
        if (nestedStat.isDirectory() || nestedStat.isSymbolicLink()) {
          queue.push(join(canonicalPackage, "node_modules"));
        }
      } catch {
        // A package does not need a private node_modules directory.
      }
    }
  }
  return packages;
}

function productionSourceFiles(root) {
  const files = [];
  const queue = SOURCE_ROOTS.map((directory) => join(root, directory));
  while (queue.length > 0) {
    const directory = queue.shift();
    let directoryEntries;
    try {
      directoryEntries = readdirSync(directory, { withFileTypes: true });
    } catch {
      fail("source_tree_unreadable");
    }
    for (const entry of directoryEntries) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "node_modules") queue.push(path);
        continue;
      }
      if (!entry.isFile()) continue;
      if (entry.name.includes(".test.") || entry.name.includes(".spec.")) continue;
      if (SOURCE_SUFFIXES.some((suffix) => entry.name.endsWith(suffix))) files.push(path);
    }
  }
  return files;
}

function verifySourceImports(root) {
  for (const path of productionSourceFiles(root)) {
    let source;
    try {
      source = readFileSync(path, "utf8");
    } catch {
      fail("source_file_unreadable");
    }
    if (FORBIDDEN_IMPORTS.some((specifier) => source.includes(specifier))) {
      fail("forbidden_optional_import");
    }
  }
}

export function verifyProductionDependencyClosure(root) {
  let canonicalRoot;
  try {
    canonicalRoot = realpathSync(resolve(root));
  } catch {
    fail("artifact_root_unreadable");
  }
  const packages = installedPackages(canonicalRoot);
  const byName = new Map();
  for (const entry of packages) {
    const versions = byName.get(entry.name) ?? [];
    versions.push(entry.version);
    byName.set(entry.name, versions);
    if (FORBIDDEN.has(entry.name)) fail("forbidden_package_installed");
    if (entry.name === "gaxios" && entry.version.startsWith("6.")) {
      fail("legacy_optional_gaxios_installed");
    }
    if (entry.name === "google-auth-library" && entry.version.startsWith("9.")) {
      fail("legacy_optional_google_auth_installed");
    }
  }
  for (const [name, version] of REQUIRED) {
    const installed = byName.get(name) ?? [];
    if (installed.length === 0) fail("required_package_missing");
    if (installed.length !== 1) fail("required_package_duplicated");
    if (installed[0] !== version) fail("required_package_version_mismatch");
  }
  verifySourceImports(canonicalRoot);
  return Object.freeze({
    status: "ok",
    package_count: packages.length,
    required: Object.freeze(Object.fromEntries(REQUIRED)),
  });
}

function cliRoot(argv) {
  if (argv.length !== 2 || argv[0] !== "--root" || argv[1].length === 0) {
    fail("usage_invalid");
  }
  return argv[1];
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    console.log(JSON.stringify(verifyProductionDependencyClosure(cliRoot(process.argv.slice(2)))));
  } catch (error) {
    const code = error instanceof ClosureVerificationError ? error.code : "verification_failed";
    console.error(JSON.stringify({ status: "error", code }));
    process.exitCode = 1;
  }
}
