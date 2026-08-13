#!/usr/bin/env node
/**
 * Run one native CLI command while continuously observing the macOS foreground
 * application. The helper never activates or restores an app. A probe fault,
 * focus change, timeout, or missing terminal result fails closed.
 */
import { execFile, spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const asn = /^ASN:0x[0-9a-f]+-0x[0-9a-f]+:$/i;

function probeForeground() {
  return new Promise((resolve, reject) => {
    execFile("/usr/bin/lsappinfo", ["front"], { encoding: "utf8", timeout: 5_000 }, (error, stdout) => {
      if (error) return reject(new Error("foreground probe failed"));
      const value = stdout.trim();
      if (!asn.test(value)) return reject(new Error("foreground probe returned an invalid application identity"));
      resolve(value);
    });
  });
}

function parse(argv) {
  const separator = argv.indexOf("--");
  if (separator < 0 || separator === argv.length - 1) throw new Error("usage: macos-foreground-guard.mjs --result FILE --stdout FILE --stderr FILE --timeout SECONDS -- COMMAND [ARGS...]");
  const options = {};
  for (let index = 0; index < separator; index += 2) {
    const key = argv[index]; const value = argv[index + 1];
    if (!key?.startsWith("--") || !value) throw new Error("guard options require key/value pairs");
    options[key.slice(2)] = value;
  }
  const timeout = Number(options.timeout || 300);
  if (!options.result || !options.stdout || !options.stderr || !Number.isInteger(timeout) || timeout < 1 || timeout > 300) throw new Error("guard result/stdout/stderr and bounded timeout are required");
  return { ...options, timeout, command: argv[separator + 1], args: argv.slice(separator + 2) };
}

export async function guardedRun(spec) {
  const expected = await probeForeground();
  const started = new Date();
  const stdout = [];
  const stderr = [];
  let terminal = null;
  let monitorFault = null;
  let monitoring = false;
  const child = spawn(spec.command, spec.args, { cwd: spec.cwd, env: spec.env, stdio: ["ignore", "pipe", "pipe"] });
  child.stdout.on("data", (chunk) => stdout.push(Buffer.from(chunk)));
  child.stderr.on("data", (chunk) => stderr.push(Buffer.from(chunk)));
  const stopChild = () => {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill("SIGTERM");
      setTimeout(() => {
        if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
      }, 1_000).unref();
    }
  };
  const sample = async () => {
    if (monitoring || monitorFault) return;
    monitoring = true;
    try {
      const observed = await probeForeground();
      if (observed !== expected) {
        monitorFault = "macOS foreground application changed";
        stopChild();
      }
    } catch (error) {
      monitorFault = error instanceof Error ? error.message : "foreground probe failed";
      stopChild();
    } finally { monitoring = false; }
  };
  const interval = setInterval(sample, 20);
  const timeout = setTimeout(() => {
    monitorFault = "guarded command timed out";
    stopChild();
  }, spec.timeoutSeconds * 1_000);
  const exit = await new Promise((resolve) => {
    child.once("error", (error) => resolve({ code: null, signal: null, error: error.message }));
    child.once("exit", (code, signal) => resolve({ code, signal, error: null }));
  });
  clearInterval(interval); clearTimeout(timeout);
  while (monitoring) await new Promise((resolve) => setTimeout(resolve, 5));
  await sample();
  terminal = {
    schema: "omi.macos-foreground-guard/v1",
    status: exit.code,
    signal: exit.signal,
    error: exit.error,
    monitor_error: monitorFault,
    interval_milliseconds: 20,
    policy: "bounded-20ms-macos-foreground-change-detection-no-activation-request",
    started_at: started.toISOString(),
    finished_at: new Date().toISOString(),
  };
  return { terminal, stdout: Buffer.concat(stdout), stderr: Buffer.concat(stderr) };
}

async function main() {
  const options = parse(process.argv.slice(2));
  for (const file of [options.result, options.stdout, options.stderr]) mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
  const run = await guardedRun({ command: options.command, args: options.args, cwd: process.cwd(), env: process.env, timeoutSeconds: options.timeout });
  writeFileSync(options.stdout, run.stdout, { mode: 0o600 });
  writeFileSync(options.stderr, run.stderr, { mode: 0o600 });
  writeFileSync(options.result, `${JSON.stringify(run.terminal)}\n`, { mode: 0o600 });
  if (run.terminal.monitor_error || run.terminal.error || run.terminal.status !== 0) process.exitCode = 2;
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  main().catch((error) => { console.error(`ERROR: ${error.message}`); process.exitCode = 2; });
}
