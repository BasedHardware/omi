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
    execFile("/usr/bin/lsappinfo", ["front"], { encoding: "utf8", timeout: 250 }, (error, stdout) => {
      if (error) return reject(new Error("foreground probe failed"));
      const value = stdout.trim();
      if (!asn.test(value)) return reject(new Error("foreground probe returned an invalid application identity"));
      execFile("/usr/bin/lsappinfo", ["info", "-only", "bundleID", "-app", value], { encoding: "utf8", timeout: 250 }, (infoError, infoStdout) => {
        if (infoError) return reject(new Error("foreground metadata probe failed"));
        const match = infoStdout.match(/"CFBundleIdentifier"="([A-Za-z0-9.-]+)"/);
        if (!match) return reject(new Error("foreground metadata probe returned no bundle identity"));
        resolve({ identity: value, bundleId: match[1] });
      });
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
  const forbiddenBundleIds = String(options["forbid-bundle-ids"] || "").split(",").filter(Boolean);
  if (!forbiddenBundleIds.length || forbiddenBundleIds.some((value) => !/^[A-Za-z0-9][A-Za-z0-9.-]{1,127}$/.test(value))) throw new Error("guard requires bounded --forbid-bundle-ids");
  return { ...options, timeout, forbiddenBundleIds, command: argv[separator + 1], args: argv.slice(separator + 2) };
}

export async function guardedRun(spec) {
  const started = new Date();
  let initial;
  try {
    initial = await probeForeground();
  } catch (error) {
    return {
      terminal: {
        schema: "omi.macos-foreground-guard/v1", status: 2, signal: null, error: null,
        monitor_error: error.message, target_interval_milliseconds: 20,
        probe_timeout_milliseconds: 250, sample_count: 0,
        max_sample_gap_milliseconds: 0, forbidden_bundle_ids: [...spec.forbiddenBundleIds].sort(),
        policy: "sampled-macos-forbidden-fixture-foreground-detection-20ms-target-250ms-probe-timeout-no-activation-request",
        started_at: started.toISOString(), finished_at: new Date().toISOString(),
      },
      stdout: Buffer.alloc(0), stderr: Buffer.alloc(0),
    };
  }
  if (spec.forbiddenBundleIds.includes(initial.bundleId)) {
    return {
      terminal: {
        schema: "omi.macos-foreground-guard/v1", status: 2, signal: null, error: null,
        monitor_error: "a forbidden fixture application is already foreground",
        target_interval_milliseconds: 20, probe_timeout_milliseconds: 250,
        sample_count: 1, max_sample_gap_milliseconds: 0,
        forbidden_bundle_ids: [...spec.forbiddenBundleIds].sort(),
        policy: "sampled-macos-forbidden-fixture-foreground-detection-20ms-target-250ms-probe-timeout-no-activation-request",
        started_at: started.toISOString(), finished_at: new Date().toISOString(),
      },
      stdout: Buffer.alloc(0), stderr: Buffer.alloc(0),
    };
  }
  const stdout = [];
  const stderr = [];
  let terminal = null;
  let monitorFault = null;
  let monitoring = false;
  let sampleCount = 0;
  let previousSampleAt = Date.now();
  let maxSampleGapMilliseconds = 0;
  const child = spawn(spec.command, spec.args, { cwd: spec.cwd, env: spec.env, detached: true, stdio: ["ignore", "pipe", "pipe"] });
  child.stdout.on("data", (chunk) => stdout.push(Buffer.from(chunk)));
  child.stderr.on("data", (chunk) => stderr.push(Buffer.from(chunk)));
  const groupAlive = () => {
    try { process.kill(-child.pid, 0); return true; }
    catch (error) { return error?.code !== "ESRCH"; }
  };
  let terminationPromise = null;
  const stopChild = () => {
    if (terminationPromise) return terminationPromise;
    terminationPromise = (async () => {
      if (groupAlive()) {
        try { process.kill(-child.pid, "SIGTERM"); } catch (error) { if (error?.code !== "ESRCH") child.kill("SIGTERM"); }
      }
      await new Promise((resolve) => setTimeout(resolve, 1_000));
      // Escalate against the process group even when its original leader has
      // already exited; a descendant may have ignored TERM while retaining the
      // same group id.
      if (groupAlive()) {
        try { process.kill(-child.pid, "SIGKILL"); } catch (error) { if (error?.code !== "ESRCH") child.kill("SIGKILL"); }
      }
      const deadline = Date.now() + 1_000;
      while (groupAlive() && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 10));
      if (groupAlive()) monitorFault ||= "guarded command group cleanup could not be established";
    })();
    return terminationPromise;
  };
  const sample = async () => {
    if (monitoring || monitorFault) return;
    monitoring = true;
    const sampleAt = Date.now();
    maxSampleGapMilliseconds = Math.max(maxSampleGapMilliseconds, sampleAt - previousSampleAt);
    previousSampleAt = sampleAt;
    sampleCount += 1;
    try {
      const observed = await probeForeground();
      if (spec.forbiddenBundleIds.includes(observed.bundleId)) {
        monitorFault = "a forbidden fixture application became foreground";
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
  let resolveClose;
  const closed = new Promise((resolve) => { resolveClose = resolve; });
  child.once("error", (error) => resolveClose({ code: null, signal: null, error: error.message }));
  child.once("close", (code, signal) => resolveClose({ code, signal, error: null }));
  const interrupt = (signal) => {
    monitorFault ||= `guard interrupted by ${signal}`;
    stopChild();
  };
  const interruptSigint = () => interrupt("SIGINT");
  const interruptSigterm = () => interrupt("SIGTERM");
  process.once("SIGINT", interruptSigint);
  process.once("SIGTERM", interruptSigterm);
  const exit = await Promise.race([closed, new Promise((resolve) => {
    setTimeout(() => {
      monitorFault ||= "guarded command did not close after termination";
      stopChild();
      resolve({ code: null, signal: "SIGKILL", error: "guarded command close deadline exceeded" });
    }, (spec.timeoutSeconds * 1_000) + 2_500).unref();
  })]);
  if (terminationPromise) await terminationPromise;
  process.removeListener("SIGINT", interruptSigint);
  process.removeListener("SIGTERM", interruptSigterm);
  clearInterval(interval); clearTimeout(timeout);
  while (monitoring) await new Promise((resolve) => setTimeout(resolve, 5));
  await sample();
  terminal = {
    schema: "omi.macos-foreground-guard/v1",
    status: exit.code,
    signal: exit.signal,
    error: exit.error,
    monitor_error: monitorFault,
    target_interval_milliseconds: 20,
    probe_timeout_milliseconds: 250,
    sample_count: sampleCount,
    max_sample_gap_milliseconds: maxSampleGapMilliseconds,
    forbidden_bundle_ids: [...spec.forbiddenBundleIds].sort(),
    policy: "sampled-macos-forbidden-fixture-foreground-detection-20ms-target-250ms-probe-timeout-no-activation-request",
    started_at: started.toISOString(),
    finished_at: new Date().toISOString(),
  };
  return { terminal, stdout: Buffer.concat(stdout), stderr: Buffer.concat(stderr) };
}

async function main() {
  const options = parse(process.argv.slice(2));
  for (const file of [options.result, options.stdout, options.stderr]) mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
  const run = await guardedRun({ command: options.command, args: options.args, cwd: process.cwd(), env: process.env, timeoutSeconds: options.timeout, forbiddenBundleIds: options.forbiddenBundleIds });
  writeFileSync(options.stdout, run.stdout, { mode: 0o600 });
  writeFileSync(options.stderr, run.stderr, { mode: 0o600 });
  writeFileSync(options.result, `${JSON.stringify(run.terminal)}\n`, { mode: 0o600 });
  if (run.terminal.monitor_error || run.terminal.error || run.terminal.status !== 0) process.exitCode = 2;
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  main().catch((error) => { console.error(`ERROR: ${error.message}`); process.exitCode = 2; });
}
