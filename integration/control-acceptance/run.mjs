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
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { buildDriverSource } from "./driver-source.mjs";
import {
  GATEWAY_REQUEST_LOG_NAME,
  JOURNEY_STEP_SLUGS,
  aggregate,
  applyChatProvenance,
  applyJourneyChat,
  lastGatewayRequest,
  parseServedMemoryProjections,
  PENDING_VALUE,
  readServiceBoot,
  reportFromProbeText,
  stripServedMemoryRecord,
} from "./verdict.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const PLATFORM_ROOT = join(HERE, "..", "..");
const DRIVER_PATH = join(HERE, "driver.js");
const PRODUCTION_SERVICE_URL = "http://127.0.0.1:4851";
const PRODUCTION_GATEWAY_TEST = "http://127.0.0.1:8788";
const PRODUCTION_GATEWAY_REAL = "http://127.0.0.1:8791";
const APP_NAME = "omi-on-control-acceptance";
const JOURNEY_APP_NAME = "omi-on-journey-acceptance";

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

function getJson(url, token) {
  const result = spawnSync("curl", [
    "-fsS",
    "--max-time",
    "5",
    "-H",
    `Authorization: Bearer ${token}`,
    url,
  ], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) return null;
  try {
    return JSON.parse(result.stdout);
  } catch {
    return null;
  }
}

function conversationIdsFrom(payload) {
  const rows = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.items)
      ? payload.items
      : [];
  return rows
    .map((row) => (row && typeof row.id === "string" ? row.id : null))
    .filter((id) => typeof id === "string" && id.length > 0);
}

function memoryRecordsFrom(payload) {
  const rows = Array.isArray(payload?.items) ? payload.items : [];
  return rows
    .filter((row) => row && typeof row.id === "string" && typeof row.text === "string")
    .map((row) => ({ id: row.id, text: row.text }));
}

const { REPO_PATHS } = await import("../lib/provenance.mjs");
const launcher = join(REPO_PATHS["core-foundation"], "frontend/shells/macos/scripts/dev-run-macos.sh");
const stack = join(PLATFORM_ROOT, "integration/dev-stack.sh");

const SCREEN_PROOF = process.argv.includes("--screen-proof");
const JOURNEY = process.argv.includes("--journey");
const SEAM_BREAK = process.argv.includes("--seam-break");

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  process.stdout.write(
    [
      "usage: node integration/control-acceptance/run.mjs [--screen-proof | --journey [--seam-break]]",
      "",
      "Sibling of integration/dev-app.sh --accept. Drives Home, Chat, Listen,",
      "Rewind, and every chrome route in the built macOS shell against the live",
      "local stack. Prints CONTROL <slug>=<verdict> lines, a skip list, and",
      "CONTROL-ACCEPTANCE status=PASS|FAIL.",
      "",
      "--screen-proof  only the Rewind capture control + omiScreenBridge round",
      "                trip. Does not send Chat. Use this when the local service",
      "                is already serving and the canned gateway is not paired with it.",
      "--journey       listen → conversation → memory → Home → chat retrieval,",
      "                one chain, no hop stubbed. Held out of L3; run as L4.",
      "--seam-break    with --journey: leave listen/memory/chat endpoints healthy",
      "                and drop the identified memory from the served request",
      "                before judging retrieval. The journey must fail.",
      "",
      "OMI_CHAT_MODEL=real uses the local real-model proxy; default is the canned",
      "gateway. A full or journey run always boots a leased stack so it does not contend",
      "with a long-lived 4851 holder. Never points at api.omi.me.",
    ].join("\n") + "\n",
  );
  process.exit(0);
}

if (SCREEN_PROOF && JOURNEY) fail("ERROR: --screen-proof and --journey are mutually exclusive.", 2);
if (SEAM_BREAK && !JOURNEY) fail("ERROR: --seam-break requires --journey.", 2);

switch (process.env.OMI_CHAT_MODEL ?? "") {
  case "":
  case "test":
  case "real":
    break;
  default:
    fail("ERROR: OMI_CHAT_MODEL must be unset, test, or real.", 2);
}

const gatewayUrl = process.env.OMI_CHAT_MODEL === "real" ? PRODUCTION_GATEWAY_REAL : PRODUCTION_GATEWAY_TEST;
if (PRODUCTION_SERVICE_URL.includes("api.omi.me") || gatewayUrl.includes("api.omi.me")) {
  fail("ERROR: refusing a production origin.", 2);
}

if (SCREEN_PROOF) {
  const serviceUp = serving(PRODUCTION_SERVICE_URL);
  if (!serviceUp) {
    fail("ERROR: --screen-proof needs a reachable local service on 4851.");
  }
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

if (!SCREEN_PROOF) {
  // Verification never attaches to 4851/8788/8791. Those ports are the
  // long-lived human stack; a listener there is not this run. A real-model proxy is bound on 8791 only for someone else's stack, not this leased boot.
  const up = spawnSync(stack, ["--up", "--lease"], {
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
let serviceUrl = PRODUCTION_SERVICE_URL;
let surfacePort = "5290";
let runScopedDir = "";
try {
  const owner = JSON.parse(readFileSync(ownerPath, "utf8"));
  const ready = JSON.parse(readFileSync(owner.readinessPath, "utf8"));
  if (typeof ready.devToken !== "string" || ready.devToken.length === 0) throw new Error("empty");
  token = ready.devToken;
  if (typeof ready.baseUrl === "string" && ready.baseUrl.startsWith("http://127.0.0.1:")) {
    serviceUrl = ready.baseUrl;
  }
  // The canned gateway appends gateway-requests.jsonl next to its ready file,
  // which is the run-scoped directory (`runs/<id>/`), not the stack rundir that
  // holds service-owner.json. Reading the owner-dir log produced empty served
  // items and CONTROL chat.memory=memory-not-retrieved while the page and the
  // model had the fact.
  runScopedDir = dirname(owner.readinessPath);
} catch {
  fail("ERROR: stack owner record did not yield a readiness token.");
}
const leasePath = join(dirname(ownerPath), "port-lease.json");
if (existsSync(leasePath)) {
  try {
    const lease = JSON.parse(readFileSync(leasePath, "utf8"));
    if (typeof lease?.urls?.service === "string") serviceUrl = lease.urls.service;
    // macOS origin stays 5290: the launcher pin is sibling-owned. A leased
    // surface port here would be a silent drift, not a concurrent stack.
  } catch {
    fail("ERROR: stack port lease record is unreadable.");
  }
}

let baseline = { conversationIds: [], memoryIds: [] };
if (JOURNEY) {
  const conversations = getJson(`${serviceUrl}/v1/conversations?offset=0&limit=100`, token);
  const memories = getJson(`${serviceUrl}/v1/memories?limit=100`, token);
  baseline = {
    conversationIds: conversationIdsFrom(conversations),
    memoryIds: memoryRecordsFrom(memories).map((row) => row.id),
  };
}

// Newlines stay intact: execve carries them through the launcher untouched,
// and flattening them lets a `//` line comment swallow the rest of the program.
const driver = buildDriverSource(readFileSync(DRIVER_PATH, "utf8"), {
  screenProof: SCREEN_PROOF,
  journey: JOURNEY,
  baseline,
});
const appName = JOURNEY ? JOURNEY_APP_NAME : APP_NAME;
const childEnv = {
  ...process.env,
  OMI_API_TOKEN: token,
  OMI_API_BASE_URL: serviceUrl,
  OMI_SURFACE_PORT: surfacePort,
  OMI_APP_NAME: appName,
  OMI_BUILD_DIR: buildDir,
  OMI_PROBE_JS: driver,
  OMI_PROBE_EXIT: "1",
  OMI_PROBE_PENDING_VALUE: PENDING_VALUE,
  // The macOS probe hook clamps this at 100 (`min(..., 100)` in main.swift).
  OMI_PROBE_MAX_ATTEMPTS: "100",
  OMI_PROBE_RETRY_INTERVAL: "0.4",
  OMI_PROBE_DELAY: "5",
  OMI_PROBE_SETTLE: "2",
  OMI_ACCEPTANCE_WAIT_SECONDS: JOURNEY ? "240" : "180",
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
const launched = spawnSync(launcher, ["--api", serviceUrl, "--route", JOURNEY ? "listen" : "home"], {
  cwd: dirname(launcher),
  env: childEnv,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "pipe"],
});
const elapsedMs = Date.now() - started;
const logPath = join(buildDir, `${appName}.run.log`);
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
  if (JOURNEY) {
    const parsed = reportFromProbeText(logText, { slugs: JOURNEY_STEP_SLUGS, allowSkip: false });
    if (!parsed.parse?.ok) return parsed;
    let boot = null;
    try {
      boot = readServiceBoot(readFileSync(join(dirname(ownerPath), "logs", "service.jsonl"), "utf8"));
    } catch {
      boot = null;
    }
    const memoriesAfter = memoryRecordsFrom(getJson(`${serviceUrl}/v1/memories?limit=100`, token));
    let servedLog = "";
    try {
      servedLog = readFileSync(join(runScopedDir, GATEWAY_REQUEST_LOG_NAME), "utf8");
    } catch {
      servedLog = "";
    }
    const served = lastGatewayRequest(servedLog);
    const servedItems = parseServedMemoryProjections(served?.messages ?? []);
    const memoryId = parsed.parse.result.witnesses?.memoryId ?? null;
    const record = memoriesAfter.find((row) => row.id === memoryId);
    const retrievalItems = SEAM_BREAK
      ? stripServedMemoryRecord(servedItems, record?.text)
      : servedItems;
    if (SEAM_BREAK) {
      const bySlug = new Map((parsed.parse.result.steps ?? []).map((step) => [step.slug, step.verdict]));
      const endpointSteps = [
        { slug: "mic", verdict: bySlug.get("mic") ?? "missing-step" },
        { slug: "conversation", verdict: bySlug.get("conversation") ?? "missing-step" },
        { slug: "memory", verdict: bySlug.get("memory") ?? "missing-step" },
        { slug: "home.memory", verdict: bySlug.get("home.memory") ?? "missing-step" },
        { slug: "chat", verdict: "streamed-and-persisted" },
      ];
      const endpoints = aggregate(endpointSteps, {
        slugs: ["mic", "conversation", "memory", "home.memory", "chat"],
        allowSkip: false,
      });
      process.stdout.write("SEAM-BREAK endpoints (hops still healthy; link stripped from served request):\n");
      printReport(endpoints);
    }
    const steps = applyJourneyChat(parsed.parse.result.steps, {
      intent: process.env.OMI_CHAT_MODEL === "real" ? "real" : "test",
      boot,
      rendered: parsed.parse.result.witnesses?.chat ?? null,
      retrieval: {
        memoryId,
        memories: memoriesAfter,
        servedItems: retrievalItems,
      },
    });
    const next = aggregate(steps, { slugs: JOURNEY_STEP_SLUGS, allowSkip: false });
    return { ...next, parse: parsed.parse };
  }
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
const mode = JOURNEY ? "journey" : SCREEN_PROOF ? "screen-proof" : "full";
process.stdout.write(`control-acceptance mode=${mode} wall-clock=${elapsedMs}ms launcher-status=${launched.status ?? "none"}\n`);
printReport(report);

if (launched.status !== 0 && report.parse?.reason === "probe-missing") {
  process.stderr.write("ERROR: macOS launcher exited before a PROBE_JS line.\n");
  const tail = logText.trim().split(/\n/).slice(-30).join("\n");
  if (tail) process.stderr.write(`${tail}\n`);
}

process.exit(report.status === "PASS" ? 0 : 1);
