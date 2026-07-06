/**
 * Query-time discovery of user-installed external adapter CLIs.
 *
 * Swift seeds OMI_{HERMES,OPENCLAW,CODEX}_ADAPTER_COMMAND into the bridge
 * environment at process start (AgentRuntimeProcess.applyLocalAgentEnvironment),
 * but that snapshot goes stale when an agent is installed mid-session — e.g.
 * through the floating-bar install-help flow. The bridge process keeps running,
 * so without a re-scan the freshly installed agent stays "not available" until
 * the app restarts. This module mirrors the Swift detector's search directories
 * and command construction so the ensure*Adapter paths can pick up new installs
 * without a bridge restart.
 */

import { accessSync, constants } from "fs";
import { homedir } from "os";
import { dirname, join } from "path";
import { ADAPTER_ACTIVATION_ENV } from "./adapter-selection.js";

export type DiscoverableAdapterId = "hermes" | "openclaw" | "codex";

const ADAPTER_EXECUTABLE_NAMES: Record<DiscoverableAdapterId, string> = {
  hermes: "hermes",
  openclaw: "openclaw",
  codex: "codex",
};

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, "'\\''")}'`;
}

function isExecutableFile(path: string): boolean {
  try {
    accessSync(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

/** Same search order as Swift's LocalAgentProviderDetector / AgentRuntimeProcess. */
function adapterSearchDirectories(env: NodeJS.ProcessEnv): string[] {
  const home = env.HOME?.trim() || homedir();
  const candidates = [
    ...(env.PATH ?? "").split(":"),
    join(home, ".hermes", "hermes-agent", "venv", "bin"),
    join(home, ".hermes", "node", "bin"),
    join(home, ".hermes", "hermes-agent"),
    join(home, ".openclaw", "bin"),
    join(home, ".openclaw", "node", "bin"),
    join(home, ".local", "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
  ];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const dir of candidates) {
    if (!dir || seen.has(dir)) continue;
    seen.add(dir);
    result.push(dir);
  }
  return result;
}

function firstExecutable(name: string, env: NodeJS.ProcessEnv): string | undefined {
  for (const dir of adapterSearchDirectories(env)) {
    const path = join(dir, name);
    if (isExecutableFile(path)) return path;
  }
  return undefined;
}

/** Mirrors AgentRuntimeProcess's per-adapter command construction. */
export function adapterCommandForExecutable(
  adapterId: DiscoverableAdapterId,
  executablePath: string
): string {
  if (adapterId === "codex") {
    return shellQuote(executablePath);
  }
  if (adapterId === "openclaw") {
    const siblingNode = join(dirname(executablePath), "node");
    if (isExecutableFile(siblingNode)) {
      return `${shellQuote(siblingNode)} ${shellQuote(executablePath)} acp`;
    }
    return `${shellQuote(executablePath)} acp`;
  }
  return `${shellQuote(executablePath)} acp`;
}

/**
 * Ensure the activation env var for an external adapter is populated.
 * Returns the command if the adapter is (or becomes) activated, else undefined.
 * Mutates `env` in place when a fresh install is discovered so subsequent
 * adapterIsActivated checks and adapter start() calls see the command.
 */
export function discoverAdapterCommand(
  adapterId: DiscoverableAdapterId,
  env: NodeJS.ProcessEnv = process.env
): string | undefined {
  const envName = ADAPTER_ACTIVATION_ENV[adapterId];
  const existing = env[envName]?.trim();
  if (existing) return existing;
  const executablePath = firstExecutable(ADAPTER_EXECUTABLE_NAMES[adapterId], env);
  if (!executablePath) return undefined;
  const command = adapterCommandForExecutable(adapterId, executablePath);
  env[envName] = command;
  return command;
}
