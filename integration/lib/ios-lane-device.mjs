import { spawn, execFileSync, spawnSync } from "node:child_process";
import { closeSync, existsSync, openSync, readFileSync } from "node:fs";

export const SIMULATOR_UDID_PATTERN =
  /^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$/;

export function isIosStackAssertCommand(command) {
  return /(?:^|[\s/])dev-stack\.sh(?:\s|$)/.test(command)
    && /(?:^|\s)--assert(?:\s|$)/.test(command);
}

export function appendDeviceArgument(command, udid) {
  if (!udid) return command;
  if (!isIosStackAssertCommand(command)) return command;
  if (/(?:^|\s)--device(?:\s|$)/.test(command)) return command;
  if (!SIMULATOR_UDID_PATTERN.test(udid)) {
    throw new Error(`refusing to pass a non-UDID --device value: ${udid}`);
  }
  return `${command} --device ${udid}`;
}

function holderStillAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  const result = spawnSync("ps", ["-p", String(pid), "-o", "state="], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) return false;
  const state = (result.stdout ?? "").trim();
  return state.length > 0 && !state.startsWith("Z");
}

function readLeaseRecord(outPath) {
  try {
    const parsed = JSON.parse(readFileSync(outPath, "utf8"));
    if (typeof parsed?.udid === "string" && SIMULATOR_UDID_PATTERN.test(parsed.udid)) return parsed;
  } catch {
    // incomplete write
  }
  return null;
}

/**
 * Spawn the simulator-lease holder and wait until it writes the UDID.
 * The holder stays alive until release() or the parent pid dies.
 */
export function holdSimulatorLease({
  holderScript,
  runId,
  outPath,
  parentPid,
  leaseRoot = undefined,
  bunPath = "bun",
  readyTimeoutMs = 180_000,
}) {
  const args = [holderScript, "hold", "--run-id", runId, "--out", outPath, "--parent-pid", String(parentPid)];
  if (leaseRoot) args.push("--lease-root", leaseRoot);
  const logPath = `${outPath}.holder.log`;
  const logFd = openSync(logPath, "w");
  const child = spawn(bunPath, args, {
    stdio: ["ignore", "ignore", logFd],
    detached: true,
  });
  closeSync(logFd);
  child.unref();

  const started = Date.now();
  let parsed = null;
  while ((parsed = readLeaseRecord(outPath)) === null) {
    if (!holderStillAlive(child.pid)) {
      const detail = existsSync(logPath) ? readFileSync(logPath, "utf8").trim() : "";
      throw new Error(detail || `simulator lease holder exited before writing ${outPath}`);
    }
    if (Date.now() - started > readyTimeoutMs) {
      try {
        process.kill(child.pid, "SIGTERM");
      } catch {
        // already gone
      }
      const detail = existsSync(logPath) ? readFileSync(logPath, "utf8").trim() : "";
      throw new Error(detail || `simulator lease holder did not write ${outPath} within ${readyTimeoutMs}ms`);
    }
    execFileSync("sleep", ["0.05"], { stdio: "ignore" });
  }

  let released = false;
  return {
    udid: parsed.udid,
    name: typeof parsed.name === "string" ? parsed.name : parsed.udid,
    release: () => {
      if (released) return;
      released = true;
      if (!holderStillAlive(child.pid)) return;
      try {
        process.kill(child.pid, "SIGTERM");
      } catch {
        // already gone
      }
    },
  };
}
