#!/usr/bin/env node
// Sibling of `integration/dev-app.sh --accept`. That path snapshots the app and
// counts host-observed HTTP; this path clicks the real controls in the built
// macOS shell and fails on a dead one.
//
// Does not edit frontend/shells — it launches the existing
// `scripts/dev-run-macos.sh` with OMI_PROBE_JS (already a host hook).
//
// usage: node integration/control-acceptance/run.mjs

import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { buildDriverSource } from "./driver-source.mjs";
import {
  aggregate,
  applyChatProvenance,
  PENDING_VALUE,
  readServiceBoot,
  reportFromProbeText,
} from "./verdict.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const PLATFORM_ROOT = join(HERE, "..", "..");
const DRIVER_PATH = join(HERE, "driver.js");
const SERVICE_URL = "http://127.0.0.1:4851";
const GATEWAY_TEST = "http://127.0.0.1:8788";
const GATEWAY_REAL = "http://127.0.0.1:8791";
const APP_NAME = "omi-on-control-acceptance";

function fail(message, code = 1) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

function serving(url) {
  const result = spawnSync("curl", ["-fsS", "--max-time", "1", `${url}/ready`], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return result.status === 0;
}

function printReport(report) {
  for (const line of report.lines) process.stdout.write(`${line}\n`);
  process.stdout.write(`${report.skipList}\n`);
  process.stdout.write(`${report.summary}\n`);
}

const { REPO_PATHS } = await import("../lib/provenance.mjs");
const launcher = join(REPO_PATHS["core-foundation"], "frontend/shells/macos/scripts/dev-run-macos.sh");
const stack = join(PLATFORM_ROOT, "integration/dev-stack.sh");

const SCREEN_PROOF = process.argv.includes("--screen-proof");

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  process.stdout.write(
    [
      "usage: node integration/control-acceptance/run.mjs [--screen-proof]",
      "",
      "Sibling of integration/dev-app.sh --accept. Drives Home, Chat, Listen,",
      "Rewind, and every chrome route in the built macOS shell against the live",
      "local stack. Prints CONTROL <slug>=<verdict> lines, a skip list, and",
      "CONTROL-ACCEPTANCE status=PASS|FAIL.",
      "",
      "--screen-proof  only the Rewind capture control + omiScreenBridge round",
      "                trip. Does not send Chat. Use this when 4851 is already",
      "                serving and the canned gateway is not paired with it.",
      "",
      "OMI_CHAT_MODEL=real uses the local real-model proxy on 8791; default is",
      "the canned gateway on 8788. Never points at api.omi.me.",
    ].join("\n") + "\n",
  );
  process.exit(0);
}

switch (process.env.OMI_CHAT_MODEL ?? "") {
  case "":
  case "test":
  case "real":
    break;
  default:
    fail("ERROR: OMI_CHAT_MODEL must be unset, test, or real.", 2);
}

const gatewayUrl = process.env.OMI_CHAT_MODEL === "real" ? GATEWAY_REAL : GATEWAY_TEST;
if (SERVICE_URL.includes("api.omi.me") || gatewayUrl.includes("api.omi.me")) {
  fail("ERROR: refusing a production origin.", 2);
}

const serviceUp = serving(SERVICE_URL);
const gatewayUp = serving(gatewayUrl);
const realProxyUp = serving(GATEWAY_REAL);
if (!SCREEN_PROOF && process.env.OMI_CHAT_MODEL !== "real" && realProxyUp) {
  fail(
    "ERROR: real-model proxy is bound on 8791 while OMI_CHAT_MODEL is not real. Stop that stack or set OMI_CHAT_MODEL=real.",
  );
}
if (!SCREEN_PROOF && serviceUp !== gatewayUp) {
  fail(
    `ERROR: partial stack (service ${serviceUp ? "up" : "down"}, gateway ${gatewayUp ? "up" : "down"}). Stop it with integration/dev-stack.sh --stop`,
  );
}
if (SCREEN_PROOF && !serviceUp) {
  fail("ERROR: --screen-proof needs a reachable local service on 4851.");
}

const runDir = mkdtempSync(join(tmpdir(), "omi-control-acceptance-"));
const buildDir = join(runDir, "build");
let booted = false;
const stopIfBooted = () => {
  if (!booted) return;
  spawnSync(stack, ["--stop"], {
    cwd: PLATFORM_ROOT,
    env: { ...process.env, OMI_DEV_STACK_RUNDIR: runDir },
    stdio: "inherit",
  });
};
process.on("exit", stopIfBooted);
process.on("SIGINT", () => {
  stopIfBooted();
  process.exit(130);
});

if (!SCREEN_PROOF && !serviceUp && !gatewayUp) {
  const up = spawnSync(stack, ["--up"], {
    cwd: PLATFORM_ROOT,
    env: { ...process.env, OMI_SEED_PERSONA: "demo", OMI_DEV_STACK_RUNDIR: runDir },
    stdio: "inherit",
  });
  if (up.status !== 0) fail("ERROR: could not boot the local stack.");
  booted = true;
}

const ownerPath = booted
  ? join(runDir, "service-owner.json")
  : join(process.env.OMI_DEV_STACK_RUNDIR || "/tmp/omi-dev-stack", "service-owner.json");

let token = "";
try {
  const owner = JSON.parse(readFileSync(ownerPath, "utf8"));
  const ready = JSON.parse(readFileSync(owner.readinessPath, "utf8"));
  if (typeof ready.devToken !== "string" || ready.devToken.length === 0) throw new Error("empty");
  token = ready.devToken;
} catch {
  fail("ERROR: stack owner record did not yield a readiness token.");
}

// Newlines stay intact: execve carries them through the launcher untouched,
// and flattening them lets a `//` line comment swallow the rest of the program.
const driver = buildDriverSource(readFileSync(DRIVER_PATH, "utf8"), { screenProof: SCREEN_PROOF });
const childEnv = {
  ...process.env,
  OMI_API_TOKEN: token,
  OMI_API_BASE_URL: SERVICE_URL,
  OMI_SURFACE_PORT: "5290",
  OMI_APP_NAME: APP_NAME,
  OMI_BUILD_DIR: buildDir,
  OMI_PROBE_JS: driver,
  OMI_PROBE_EXIT: "1",
  OMI_PROBE_PENDING_VALUE: PENDING_VALUE,
  // The macOS probe hook clamps this at 100 (`min(..., 100)` in main.swift).
  OMI_PROBE_MAX_ATTEMPTS: "100",
  OMI_PROBE_RETRY_INTERVAL: "0.4",
  OMI_PROBE_DELAY: "5",
  OMI_PROBE_SETTLE: "2",
  OMI_ACCEPTANCE_WAIT_SECONDS: "180",
  OMI_READY_TIMEOUT_SECONDS: "30",
};
delete childEnv.OMI_ACCEPTANCE;
delete childEnv.OMI_ACCEPTANCE_EXIT;
delete childEnv.OMI_CONSUMER_EVIDENCE_PATH;
delete childEnv.OMI_CONSUMER_EVIDENCE_EXIT;
delete childEnv.OMI_SURFACE_URL;
delete childEnv.OMI_SURFACE_PATH;
if (SCREEN_PROOF) {
  delete childEnv.OMI_CHAT_MODEL;
  delete childEnv.GLM_API_KEY;
  delete childEnv.ZAI_API_KEY;
  delete childEnv.OMI_BENCH_OPENAI_API_KEY;
}

const started = Date.now();
const launched = spawnSync(launcher, ["--api", SERVICE_URL, "--route", "home"], {
  cwd: dirname(launcher),
  env: childEnv,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "pipe"],
});
const elapsedMs = Date.now() - started;
const logPath = join(buildDir, `${APP_NAME}.run.log`);
let logText = `${launched.stdout ?? ""}\n${launched.stderr ?? ""}`;
try {
  logText += `\n${readFileSync(logPath, "utf8")}`;
} catch {
  // Probe output lives on the run log when the launcher redirected it.
}

if (/api\.omi\.me|\?rig=dev/.test(logText)) {
  fail("ERROR: control-acceptance observed a production origin or ?rig=dev. Stopping.");
}

const report = (() => {
  const parsed = reportFromProbeText(logText);
  if (!parsed.parse?.ok || SCREEN_PROOF) return parsed;
  let boot = null;
  try {
    boot = readServiceBoot(readFileSync(join(dirname(ownerPath), "logs", "service.jsonl"), "utf8"));
  } catch {
    boot = null;
  }
  const steps = applyChatProvenance(parsed.parse.result.steps, {
    intent: process.env.OMI_CHAT_MODEL === "real" ? "real" : "test",
    boot,
    rendered: parsed.parse.result.witnesses?.chat ?? null,
  });
  const next = aggregate(steps);
  return { ...next, parse: parsed.parse };
})();
process.stdout.write(`control-acceptance wall-clock=${elapsedMs}ms launcher-status=${launched.status ?? "none"}\n`);
printReport(report);

if (launched.status !== 0 && report.parse?.reason === "probe-missing") {
  process.stderr.write("ERROR: macOS launcher exited before a PROBE_JS line.\n");
  const tail = logText.trim().split(/\n/).slice(-30).join("\n");
  if (tail) process.stderr.write(`${tail}\n`);
}

process.exit(report.status === "PASS" ? 0 : 1);
