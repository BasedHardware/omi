import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import {
  PRODUCTION_ARTIFACT_BUN_VERSION,
  PRODUCTION_ARTIFACT_COMMAND_MAX_BUFFER_BYTES,
  PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS,
  PRODUCTION_ARTIFACT_MAX_ALLOCATED_KIB,
  productionDependencyArtifactPlan,
} from "./production-dependency-artifact";

const fail = (code: string): never => { throw new TypeError(code); };

const outputArgument = (args: readonly string[]): string => {
  if (args.length !== 2 || args[0] !== "--output" || args[1]?.length === 0) {
    fail("production_artifact_usage_invalid");
  }
  return args[1]!;
};

const run = (command: string, args: readonly string[], cwd: string): string => {
  try {
    return execFileSync(command, [...args], {
      cwd,
      encoding: "utf8",
      env: { ...process.env },
      stdio: ["ignore", "pipe", "pipe"],
      timeout: PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS,
      maxBuffer: PRODUCTION_ARTIFACT_COMMAND_MAX_BUFFER_BYTES,
      killSignal: "SIGKILL",
    }).trim();
  } catch {
    return fail("production_artifact_command_failed");
  }
};

let outputRoot: string | null = null;
let archivePath: string | null = null;
let created = false;
try {
  const projectRoot = run("git", ["rev-parse", "--show-toplevel"], process.cwd());
  const outputValue = outputArgument(process.argv.slice(2));
  const sourceCommit = run("git", ["rev-parse", "HEAD"], projectRoot);
  const worktreeStatus = run("git", ["status", "--porcelain", "--untracked-files=all"], projectRoot);
  const plan = productionDependencyArtifactPlan({
    project_root: projectRoot,
    output_root: outputValue,
    source_commit: sourceCommit,
    bun_version: Bun.version,
    worktree_status: worktreeStatus,
  });
  outputRoot = plan.output_root;
  if (existsSync(outputRoot)) fail("production_artifact_output_exists");
  archivePath = `${outputRoot}.archive-${process.pid}.tar`;
  if (existsSync(archivePath)) fail("production_artifact_archive_exists");
  mkdirSync(dirname(outputRoot), { recursive: true });
  mkdirSync(outputRoot);
  created = true;
  run("git", ["archive", "--format=tar", "--output", archivePath, sourceCommit], projectRoot);
  run("tar", ["-xf", archivePath, "-C", outputRoot], projectRoot);
  rmSync(archivePath);
  run("bun", ["install", "--production", "--omit", "optional", "--frozen-lockfile"], outputRoot);
  const allocatedKiBText = run("du", ["-sk", outputRoot], projectRoot).split(/\s+/, 1)[0];
  const allocatedKiB = Number(allocatedKiBText);
  if (!Number.isSafeInteger(allocatedKiB) || allocatedKiB < 0
    || allocatedKiB > PRODUCTION_ARTIFACT_MAX_ALLOCATED_KIB) {
    fail("production_artifact_size_limit_exceeded");
  }
  const verification = run("node", ["scripts/verify-production-dependency-closure.mjs", "--root", outputRoot], outputRoot);
  run("bun", ["scripts/verify-firebase-auth-runtime.mjs"], outputRoot);
  writeFileSync(`${outputRoot}/PRODUCTION_DEPENDENCY_ARTIFACT.json`, `${JSON.stringify({
    version: plan.version,
    source_commit: plan.source_commit,
    bun_version: PRODUCTION_ARTIFACT_BUN_VERSION,
    allocated_kib: allocatedKiB,
    max_allocated_kib: PRODUCTION_ARTIFACT_MAX_ALLOCATED_KIB,
    command_timeout_ms: PRODUCTION_ARTIFACT_COMMAND_TIMEOUT_MS,
    dependency_verification: JSON.parse(verification),
  }, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  process.stdout.write(`${JSON.stringify({
    status: "built",
    version: plan.version,
    source_commit: plan.source_commit,
    output_root: plan.output_root,
  })}\n`);
} catch (error) {
  if (archivePath !== null && existsSync(archivePath)) rmSync(archivePath);
  if (created && outputRoot !== null && existsSync(outputRoot)) rmSync(outputRoot, { recursive: true });
  const code = error instanceof TypeError && error.message.startsWith("production_artifact_")
    ? error.message
    : "production_artifact_build_failed";
  process.stderr.write(`${JSON.stringify({ status: "error", code })}\n`);
  process.exitCode = 1;
}
