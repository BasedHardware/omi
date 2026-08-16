import { rm } from "node:fs/promises";
import { spawn } from "node:child_process";

const SIGNAL_EXIT_CODES = { SIGHUP: 129, SIGINT: 130, SIGTERM: 143 };

function usage() {
  throw new Error(
    "Usage: supervise.mjs [--timeout-seconds N|--timeout-ms N] [--grace-ms N] [--cleanup-path PATH] -- command [args...]",
  );
}

function positiveInteger(value, option) {
  if (!/^\d+$/.test(value) || Number(value) <= 0) {
    throw new Error(`${option} must be a positive integer`);
  }
  return Number(value);
}

function parseArguments(arguments_) {
  let timeoutMs = 180_000;
  let graceMs = 10_000;
  let cleanupPath;
  let index = 0;
  while (index < arguments_.length && arguments_[index] !== "--") {
    const option = arguments_[index++];
    const value = arguments_[index++];
    if (!value) usage();
    if (option === "--timeout-seconds") timeoutMs = positiveInteger(value, option) * 1_000;
    else if (option === "--timeout-ms") timeoutMs = positiveInteger(value, option);
    else if (option === "--grace-ms") graceMs = positiveInteger(value, option);
    else if (option === "--cleanup-path") cleanupPath = value;
    else usage();
  }
  if (arguments_[index] !== "--" || index + 1 >= arguments_.length) usage();
  return { timeoutMs, graceMs, cleanupPath, command: arguments_[index + 1], args: arguments_.slice(index + 2) };
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function processGroupExists(processGroupId) {
  try {
    process.kill(-processGroupId, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    // On macOS a just-terminated, reparented grandchild can briefly leave a
    // zombie process-group entry. It cannot receive signals, so it is already
    // drained for the runner's purposes; treating it as live would make the
    // supervisor report a false cleanup failure.
    if (error.code === "EPERM") return false;
    throw error;
  }
}

function signalProcessGroup(processGroupId, signal) {
  try {
    process.kill(-processGroupId, signal);
  } catch (error) {
    if (error.code !== "ESRCH") throw error;
  }
}

async function waitForProcessGroup(processGroupId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (processGroupExists(processGroupId)) {
    if (Date.now() >= deadline) return false;
    await delay(25);
  }
  return true;
}

async function terminateProcessGroup(processGroupId, initialSignal, graceMs) {
  signalProcessGroup(processGroupId, initialSignal);
  if (await waitForProcessGroup(processGroupId, graceMs)) return;
  signalProcessGroup(processGroupId, "SIGKILL");
  if (!(await waitForProcessGroup(processGroupId, graceMs))) {
    throw new Error(`Process group ${processGroupId} did not exit after SIGKILL`);
  }
}

async function removeCleanupPath(cleanupPath) {
  if (!cleanupPath) return;
  await rm(cleanupPath, { recursive: true, force: true });
  // Firebase's shutdown hooks can finish just after their foreground CLI
  // exits. Reclaim the same owned path once more after that short tail.
  await delay(100);
  await rm(cleanupPath, { recursive: true, force: true });
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const child = spawn(options.command, options.args, { detached: true, stdio: "inherit" });
  const processGroupId = child.pid;
  const childExit = new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => resolve({ code, signal }));
  });

  let interrupt;
  const interrupted = new Promise((resolve) => {
    interrupt = resolve;
  });
  const signalHandlers = new Map();
  for (const signal of Object.keys(SIGNAL_EXIT_CODES)) {
    const handler = () => interrupt({ type: "signal", signal });
    signalHandlers.set(signal, handler);
    process.once(signal, handler);
  }
  const timeout = setTimeout(() => interrupt({ type: "timeout" }), options.timeoutMs);

  let exitCode = 1;
  try {
    const event = await Promise.race([
      childExit.then((result) => ({ type: "exit", result })),
      interrupted,
    ]);
    clearTimeout(timeout);

    if (event.type === "timeout") {
      console.error(`ERROR: desktop Beta admission emulator harness exceeded ${options.timeoutMs}ms`);
      await terminateProcessGroup(processGroupId, "SIGTERM", options.graceMs);
      exitCode = 124;
    } else if (event.type === "signal") {
      await terminateProcessGroup(processGroupId, event.signal, options.graceMs);
      exitCode = SIGNAL_EXIT_CODES[event.signal];
    } else {
      // Firebase may exit before its Java emulator child. The detached group is
      // ours alone, so always drain it before reporting the runner's result.
      await terminateProcessGroup(processGroupId, "SIGTERM", options.graceMs);
      exitCode = event.result.code ?? 1;
    }
  } finally {
    clearTimeout(timeout);
    for (const [signal, handler] of signalHandlers) process.removeListener(signal, handler);
    await removeCleanupPath(options.cleanupPath);
  }
  process.exitCode = exitCode;
}

await main();
