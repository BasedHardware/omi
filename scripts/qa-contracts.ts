import { createHash } from "node:crypto";
import { lstat, readdir, readFile, readlink } from "node:fs/promises";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export interface ContractLock {
  schemaVersion: number;
  publicationStatus: string;
  package: {
    name: string;
    version: string;
    dependency: string;
  };
  artifact: {
    path: string;
    sha256: string;
    sha512: string;
    integrity: string;
    metadataPath: string;
    metadataSha256: string;
    provenancePath: string;
    provenanceSha256: string;
    sourceDigest: string;
    files: string[];
  };
  source: {
    repository: string;
    path: string;
    ref: string;
    commit: string;
    baselineCommit: string;
    upstreamBranchPushed: boolean;
    mergedToMain: boolean;
    registryPublished: boolean;
    evidence: string;
  };
  toolchain: {
    artifactBuild: {
      node: string;
      npm: string;
      pnpm: string;
      typescript: string;
    };
    adoptionVerification: {
      bun: string;
      typescript: string;
    };
  };
}

interface ArtifactRecord {
  schemaVersion: number;
  package: { name: string; version: string };
  provenanceSha256: string;
  sourceDigest: string;
  tarballSha256: string;
  files: string[];
}

interface ProvenanceRecord {
  schemaVersion: number;
  package: { name: string; version: string };
  repository: string;
  baselineCommit: string;
  compiler: { name: string; version: string };
  sourceDigest: string;
}

interface InstalledManifest {
  name?: string;
  version?: string;
  private?: boolean;
  exports?: unknown;
}

const expectedExports = {
  "./pagination/cursor": {
    types: "./dist/pagination/cursor.d.ts",
    import: "./dist/pagination/cursor.js",
  },
  "./projections/synthesized": {
    types: "./dist/projections/synthesized.d.ts",
    import: "./dist/projections/synthesized.js",
  },
  // The ratified TASKS READ wire (DAVID-tasks-read-epoch-and-ci D1/D2). Same
  // reason as every other row: `requireJsonEqual` compares the WHOLE exports
  // object, so a subpath that quietly appears or disappears in the vendored
  // tarball fails the gate rather than being absorbed. Key ORDER is part of
  // that comparison, so this sits where the package declares it.
  "./projections/tasks": {
    types: "./dist/projections/tasks.d.ts",
    import: "./dist/projections/tasks.js",
  },
  "./recall/trace": {
    types: "./dist/recall/trace.d.ts",
    import: "./dist/recall/trace.js",
  },
  // The client-facing WRITE wire (COORD-write-path-rulings B1/B2/B4/B6). It is
  // listed here for the same reason the others are: `requireJsonEqual` on the
  // whole exports object means a subpath that quietly appears or disappears in
  // the vendored tarball fails the gate rather than being absorbed.
  "./write/ops": {
    types: "./dist/write/ops.d.ts",
    import: "./dist/write/ops.js",
  },
};

function fail(message: string): never {
  throw new Error(`contract QA: ${message}`);
}

function requireEqual(label: string, actual: unknown, expected: unknown): void {
  if (actual !== expected) fail(`${label} mismatch: expected ${String(expected)}, received ${String(actual)}`);
}

function requireJsonEqual(label: string, actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) fail(`${label} mismatch`);
}

function hash(bytes: Uint8Array, algorithm: "sha256" | "sha512"): string {
  return createHash(algorithm).update(bytes).digest("hex");
}

function asBase64(hex: string): string {
  return Buffer.from(hex, "hex").toString("base64");
}

export function verifyExactFiles(label: string, actual: readonly string[], expected: readonly string[]): void {
  if (new Set(actual).size !== actual.length) fail(`${label} contains duplicate paths`);
  const actualSorted = [...actual].sort();
  const expectedSorted = [...expected].sort();
  requireJsonEqual(label, actualSorted, expectedSorted);
}

export function verifyTarballBytes(bytes: Uint8Array, artifact: ContractLock["artifact"]): void {
  const sha256 = hash(bytes, "sha256");
  const sha512 = hash(bytes, "sha512");
  requireEqual("tarball SHA-256", sha256, artifact.sha256);
  requireEqual("tarball SHA-512", sha512, artifact.sha512);
  requireEqual("tarball integrity", `sha512-${asBase64(sha512)}`, artifact.integrity);
}

export function verifyArtifactRecords(
  lock: ContractLock,
  artifact: ArtifactRecord,
  provenance: ProvenanceRecord,
): void {
  requireEqual("lock schema", lock.schemaVersion, 2);
  requireEqual("source repository", lock.source.repository, "BasedHardware/omi");

  // PUBLICATION STATE IS CHECKED FOR COHERENCE, NOT PINNED TO ONE STAGE.
  //
  // This block used to be three `requireEqual`s against literals: status ===
  // "upstream-branch-qa-evidence", upstreamBranchPushed === true, and ref === a specific
  // branch name. Every one of those was wrong in a different way.
  //
  //  - `upstreamBranchPushed === true` compared a boolean THE LOCKFILE DECLARES ABOUT
  //    ITSELF against `true`. No ls-remote, no remote of any kind. The gate asked the
  //    lockfile whether it had been pushed and the lockfile answered. Writing `true`
  //    without pushing produced a fully green gate and a false record; writing the truth
  //    broke the build. That is backwards, and it is this project's signature failure —
  //    a mechanism reporting success while the thing it claims never happened.
  //  - Pinning the status to one stage means the artifact can never legitimately BE at
  //    another stage. Pre-push is a real, honest state and had no way to be expressed.
  //  - The pinned `ref` was a stale literal from the 0.1.1 vintage naming a branch that
  //    does not exist in this workspace at all.
  //
  // So: the declared status must AGREE with the declared flags. That is genuinely
  // checkable offline and catches the incoherent combinations. It deliberately does NOT
  // claim the flags are true of the world — see verify-publication.ts, which does the
  // ls-remote and cannot live here because this runs inside a hermetic `bun test`.
  const PUBLICATION_STAGES: Record<string, { pushed: boolean; merged: boolean; registry: boolean }> = {
    "local-qa-evidence": { pushed: false, merged: false, registry: false },
    "upstream-branch-qa-evidence": { pushed: true, merged: false, registry: false },
  };
  const stage = PUBLICATION_STAGES[lock.publicationStatus];
  if (!stage) {
    fail(`unknown publication status "${lock.publicationStatus}" (known: ${Object.keys(PUBLICATION_STAGES).join(", ")})`);
  }
  requireEqual("upstream branch pushed flag", lock.source.upstreamBranchPushed, stage.pushed);
  requireEqual("merged-to-main flag", lock.source.mergedToMain, stage.merged);
  requireEqual("registry-published flag", lock.source.registryPublished, stage.registry);
  // A ref must be a well-formed branch ref. Which branch is a fact about where the source
  // lives, not a constant to be frozen here.
  if (!/^refs\/heads\/[A-Za-z0-9._\/-]+$/.test(lock.source.ref)) {
    fail(`source ref must be a refs/heads/... branch ref, got "${lock.source.ref}"`);
  }
  if (!lock.source.evidence.includes("not merged to main, registry-published, or adopted in production")) {
    fail("source evidence must state the non-production publication boundary");
  }
  if (!/^[0-9a-f]{40}$/.test(lock.source.commit)) fail("source commit must be a full Git object id");
  if (!/^[0-9a-f]{40}$/.test(lock.source.baselineCommit)) fail("baseline commit must be a full Git object id");

  requireEqual("artifact schema", artifact.schemaVersion, 1);
  requireEqual("provenance schema", provenance.schemaVersion, 1);
  requireEqual("artifact package name", artifact.package.name, lock.package.name);
  requireEqual("artifact package version", artifact.package.version, lock.package.version);
  requireEqual("provenance package name", provenance.package.name, lock.package.name);
  requireEqual("provenance package version", provenance.package.version, lock.package.version);
  requireEqual("artifact tarball digest", artifact.tarballSha256, lock.artifact.sha256);
  requireEqual("artifact provenance digest", artifact.provenanceSha256, lock.artifact.provenanceSha256);
  requireEqual("artifact source digest", artifact.sourceDigest, lock.artifact.sourceDigest);
  requireEqual("provenance source digest", provenance.sourceDigest, lock.artifact.sourceDigest);
  requireEqual("provenance repository", provenance.repository, lock.source.repository);
  requireEqual("provenance baseline", provenance.baselineCommit, lock.source.baselineCommit);
  requireEqual("provenance compiler", provenance.compiler.name, "typescript");
  requireEqual("provenance compiler version", provenance.compiler.version, lock.toolchain.artifactBuild.typescript);
  verifyExactFiles("artifact file list", artifact.files, lock.artifact.files);
}

export function verifyInstalledContract(
  lock: ContractLock,
  manifest: InstalledManifest,
  installedFiles: readonly string[],
  provenance: ProvenanceRecord,
): void {
  requireEqual("installed package name", manifest.name, lock.package.name);
  requireEqual("installed package version", manifest.version, lock.package.version);
  requireEqual("installed private flag", manifest["private"], true);
  requireJsonEqual("installed exports", manifest.exports, expectedExports);
  requireEqual("installed provenance package", provenance.package.name, lock.package.name);
  requireEqual("installed provenance version", provenance.package.version, lock.package.version);
  requireEqual("installed provenance source digest", provenance.sourceDigest, lock.artifact.sourceDigest);
  verifyExactFiles(
    "installed file list",
    installedFiles,
    lock.artifact.files.map((path) => path.replace(/^package\//, "")),
  );
}

async function listFiles(directory: string, prefix = ""): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const paths: string[] = [];
  for (const entry of entries) {
    const shown = prefix ? `${prefix}/${entry.name}` : entry.name;
    const fullPath = join(directory, entry.name);
    if (entry.isDirectory()) paths.push(...await listFiles(fullPath, shown));
    else if (entry.isFile()) paths.push(shown);
    else fail(`installed package contains a non-file entry: ${shown}`);
  }
  return paths;
}

function decode(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes);
}

function run(command: string, args: string[], cwd: string): void {
  const result = Bun.spawnSync([command, ...args], { cwd, stdout: "inherit", stderr: "inherit" });
  if (result.exitCode !== 0) fail(`${command} ${args.join(" ")} exited ${result.exitCode}`);
}

function capture(command: string, args: string[], cwd: string): string {
  const result = Bun.spawnSync([command, ...args], { cwd, stdout: "pipe", stderr: "pipe" });
  if (result.exitCode !== 0) fail(`${command} ${args.join(" ")} failed: ${decode(result.stderr)}`);
  return decode(result.stdout).trim();
}

function requireRelativeFileDependency(dependency: string): void {
  if (!dependency.startsWith("file:./")) fail("package dependency must use a relative file: path");
  if (dependency.includes("..") || dependency.includes("\\")) fail("package dependency escapes its relative vendor path");
}

async function main(): Promise<void> {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const lockBytes = await readFile(join(root, "contracts.lock.json"));
  const lock = JSON.parse(decode(lockBytes)) as ContractLock;
  const rootManifest = JSON.parse(decode(await readFile(join(root, "package.json")))) as {
    packageManager?: string;
    dependencies?: Record<string, string>;
  };

  requireEqual("root package manager", rootManifest.packageManager, `bun@${lock.toolchain.adoptionVerification.bun}`);
  requireEqual("Bun runtime", Bun.version, lock.toolchain.adoptionVerification.bun);
  requireRelativeFileDependency(lock.package.dependency);
  requireEqual("root contract dependency", rootManifest.dependencies?.[lock.package.name], lock.package.dependency);

  const artifactPath = resolve(root, lock.artifact.path);
  const metadataPath = resolve(root, lock.artifact.metadataPath);
  const provenancePath = resolve(root, lock.artifact.provenancePath);
  const vendorRoot = join(root, "vendor", "contracts");
  verifyExactFiles("vendor contract file list", await listFiles(vendorRoot), [
    relative(vendorRoot, artifactPath),
    relative(vendorRoot, metadataPath),
    relative(vendorRoot, provenancePath),
  ]);
  for (const [label, path] of [["artifact", artifactPath], ["metadata", metadataPath], ["provenance", provenancePath]] as const) {
    const stat = await lstat(path);
    if (!stat.isFile() || stat.isSymbolicLink()) fail(`${label} must be a committed regular file`);
  }

  const tarballBytes = await readFile(artifactPath);
  const metadataBytes = await readFile(metadataPath);
  const provenanceBytes = await readFile(provenancePath);
  requireEqual("artifact metadata SHA-256", hash(metadataBytes, "sha256"), lock.artifact.metadataSha256);
  requireEqual("provenance SHA-256", hash(provenanceBytes, "sha256"), lock.artifact.provenanceSha256);
  verifyTarballBytes(tarballBytes, lock.artifact);

  const artifact = JSON.parse(decode(metadataBytes)) as ArtifactRecord;
  const provenance = JSON.parse(decode(provenanceBytes)) as ProvenanceRecord;
  verifyArtifactRecords(lock, artifact, provenance);
  const archiveFiles = capture("tar", ["-tzf", artifactPath], root).split("\n").filter(Boolean);
  verifyExactFiles("tar archive file list", archiveFiles, lock.artifact.files);

  run("bun", ["install", "--frozen-lockfile", "--ignore-scripts"], root);
  const installedRoot = join(root, "node_modules", "@omi-core", "ratified-contracts");
  const installedStat = await lstat(installedRoot);
  let installedContentRoot = installedRoot;
  if (installedStat.isSymbolicLink()) {
    const linkTarget = await readlink(installedRoot);
    if (isAbsolute(linkTarget)) fail("package-manager install link must stay relative");
    installedContentRoot = resolve(dirname(installedRoot), linkTarget);
    const packageStore = join(root, "node_modules", ".bun");
    const storeRelative = relative(packageStore, installedContentRoot);
    if (storeRelative.startsWith("..") || isAbsolute(storeRelative)) {
      fail("package-manager install link must resolve inside node_modules/.bun");
    }
  } else if (!installedStat.isDirectory()) {
    fail("installed package must be a directory or Bun-managed relative link");
  }
  const installedManifest = JSON.parse(decode(await readFile(join(installedContentRoot, "package.json")))) as InstalledManifest;
  const installedProvenanceBytes = await readFile(join(installedContentRoot, "PROVENANCE.json"));
  requireEqual("installed provenance SHA-256", hash(installedProvenanceBytes, "sha256"), lock.artifact.provenanceSha256);
  const installedProvenance = JSON.parse(decode(installedProvenanceBytes)) as ProvenanceRecord;
  verifyInstalledContract(lock, installedManifest, await listFiles(installedContentRoot), installedProvenance);

  const typescriptVersion = capture(join(root, "node_modules", ".bin", "tsc"), ["--version"], root);
  requireEqual("installed TypeScript", typescriptVersion, `Version ${lock.toolchain.adoptionVerification.typescript}`);
  run(join(root, "node_modules", ".bin", "tsc"), ["-p", "tsconfig.contracts.json", "--noEmit"], root);
  run("bun", ["test", "contract-tests/ratified-contracts.test.ts", "contract-tests/qa-contracts.test.ts"], root);
  run("bun", ["test"], root);
  run("bun", ["run", "lint:imports"], root);

  console.log(JSON.stringify({
    package: `${lock.package.name}@${lock.package.version}`,
    sourceCommit: lock.source.commit,
    publicationStatus: lock.publicationStatus,
    tarballSha256: lock.artifact.sha256,
    sourceDigest: lock.artifact.sourceDigest,
    files: lock.artifact.files.length,
    verified: true,
  }, null, 2));
}

if (import.meta.main) await main();
