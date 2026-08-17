#!/usr/bin/env bun
// Re-run the numbers in docs/performance-baseline.md.
//
// Times existing seams. Does not change product behavior, does not bind 4851 or
// 5290, and does not kill a listener it did not start.
//
//   bun scripts/performance-baseline.mjs
//   bun scripts/performance-baseline.mjs --only boot,formation,chat
//   bun scripts/performance-baseline.mjs --only ui
//   bun scripts/performance-baseline.mjs --only walk
//   bun scripts/performance-baseline.mjs --only lanes --lanes L1,L2
//   bun scripts/performance-baseline.mjs --n 5
//
// JSON goes to stdout. Scratch lives under os.tmpdir(), never worktree data/.

import { spawnSync } from "node:child_process";
import {
  closeSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { tmpdir, cpus, totalmem, hostname, loadavg, uptime as osUptime } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const GATEWAY_TOKEN = "local-test-gateway-token";
const PENDING = "OMI_PERF_PENDING";
const LAUNCHER_ROUTES = [
  "home",
  "conversations",
  "memories",
  "folders",
  "tasks",
  "chat",
  "settings",
  "listen",
];
const WALK_ONLY_ROUTES = ["rewind", "apps", "brain-map"];
const CONTROL_NAV_ROUTES = [
  "home",
  "conversations",
  "memories",
  "folders",
  "tasks",
  "rewind",
  "apps",
  "brain-map",
  "chat",
  "settings",
  "listen",
];

const argv = process.argv.slice(2);
const flagValue = (name, fallback) => {
  const index = argv.indexOf(name);
  if (index === -1) return fallback;
  return argv[index + 1] ?? fallback;
};
const N = Math.max(1, Number(flagValue("--n", "5")) || 5);
const onlyRaw = flagValue("--only", "boot,ui,formation,chat,lanes");
const only = new Set(onlyRaw.split(",").map((part) => part.trim()).filter(Boolean));
const lanesRaw = flagValue("--lanes", "L1,L2,L3,L4");
const laneIds = lanesRaw.split(",").map((part) => part.trim()).filter(Boolean);
const help = argv.includes("--help") || argv.includes("-h");

if (help) {
  process.stdout.write(
    [
      "usage: bun scripts/performance-baseline.mjs [--n 5] [--only boot,ui,formation,chat,lanes] [--lanes L1,L2,L3,L4]",
      "",
      "Measures the seams named in docs/performance-baseline.md. Leases its own",
      "ports. Never binds 4851/5290. Never kills a stranger.",
      "",
    ].join("\n"),
  );
  process.exit(0);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const stats = (samples) => {
  const values = samples.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (values.length === 0) {
    return { n: 0, median: null, min: null, max: null, spread: null, samples: [] };
  }
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  return {
    n: sorted.length,
    median,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    spread: sorted[sorted.length - 1] - sorted[0],
    samples: values,
  };
};

const git = (args) => {
  const result = spawnSync("git", args, { cwd: ROOT, encoding: "utf8" });
  return result.status === 0 ? result.stdout.trim() : "";
};

const sysctl = (key) => {
  const result = spawnSync("sysctl", ["-n", key], { encoding: "utf8" });
  return result.status === 0 ? result.stdout.trim() : "";
};

const listener = (port) => {
  const result = spawnSync("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" });
  return result.status === 0 ? result.stdout.trim() : "";
};

const captureMachine = () => {
  const memBytes = Number(sysctl("hw.memsize") || totalmem());
  return {
    hostname: hostname(),
    os: `${process.platform} ${process.arch}`,
    cpu: sysctl("machdep.cpu.brand_string") || (cpus()[0]?.model ?? "unknown"),
    ncpu: Number(sysctl("hw.ncpu") || cpus().length),
    memoryGiB: Math.round(memBytes / (1024 ** 3)),
    loadavg: loadavg().map((value) => Math.round(value * 100) / 100),
    hostUptimeHours: Math.round((osUptime() / 3600) * 10) / 10,
    bun: spawnSync("bun", ["--version"], { encoding: "utf8" }).stdout.trim(),
    node: spawnSync("node", ["--version"], { encoding: "utf8" }).stdout.trim(),
    ref: git(["rev-parse", "HEAD"]),
    refShort: git(["rev-parse", "--short", "HEAD"]),
    branch: git(["rev-parse", "--abbrev-ref", "HEAD"]),
    dirty: git(["status", "--porcelain"]) !== "",
    listeners: {
      4851: Boolean(listener(4851)),
      5290: Boolean(listener(5290)),
      8788: Boolean(listener(8788)),
      8791: Boolean(listener(8791)),
    },
    measuredAt: new Date().toISOString(),
  };
};

const waitUntil = async (probe, timeoutMs, intervalMs = 5) => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const remaining = Math.max(1, deadline - Date.now());
    const hit = await Promise.race([
      Promise.resolve().then(probe),
      sleep(remaining).then(() => "timeout"),
    ]);
    if (hit === "timeout") return false;
    if (hit) return true;
    await sleep(intervalMs);
  }
  return false;
};

const curlReady = (url, requireServiceStatus = false) => {
  const result = spawnSync("curl", ["-fsS", "--max-time", "1", `${url}/ready`], { encoding: "utf8" });
  if (result.status !== 0) return false;
  if (!requireServiceStatus) return true;
  try {
    return JSON.parse(result.stdout)?.status === "ready";
  } catch {
    return false;
  }
};

const readStderr = async (child, limitMs = 500) => {
  try {
    return await Promise.race([
      new Response(child.stderr).text(),
      sleep(limitMs).then(() => ""),
    ]);
  } catch {
    return "";
  }
};

const children = [];
const remember = (child) => {
  children.push(child);
  return child;
};
const stopChild = async (child) => {
  if (!child || child.killed) return;
  child.kill("SIGTERM");
  const exited = await Promise.race([
    child.exited,
    sleep(4000).then(() => "timeout"),
  ]);
  if (exited === "timeout") child.kill("SIGKILL");
  await child.exited.catch(() => {});
};

process.on("exit", () => {
  for (const child of children) {
    try {
      child.kill("SIGTERM");
    } catch {
      // ignore
    }
  }
});

const holdLease = async (runDir, runId, roles = "service,gateway") => {
  const leasePath = join(runDir, "port-lease.json");
  const appFacingPath = join(runDir, "app-facing-test-lease.json");
  const logPath = join(runDir, "port-lease-holder.log");
  const logFd = openSync(logPath, "w");
  const child = remember(Bun.spawn([
    "bun",
    "integration/lib/stack-port-lease.ts",
    "hold",
    "--run-id",
    runId,
    "--out",
    leasePath,
    "--app-facing-lease",
    appFacingPath,
    "--roles",
    roles,
    "--parent-pid",
    String(process.pid),
  ], {
    cwd: ROOT,
    stdout: logFd,
    stderr: logFd,
  }));
  closeSync(logFd);
  const ok = await waitUntil(() => existsSync(leasePath) && existsSync(appFacingPath), 8000, 50);
  if (!ok) {
    const logText = existsSync(logPath) ? readFileSync(logPath, "utf8") : "";
    await stopChild(child);
    throw new Error(`port lease was not acquired.\n${logText}`);
  }
  const lease = JSON.parse(readFileSync(leasePath, "utf8"));
  if (lease?.urls?.service?.includes("api.omi.me") || lease?.urls?.gateway?.includes("api.omi.me")) {
    await stopChild(child);
    throw new Error("refusing a production origin");
  }
  if (roles.includes("surface")) {
    const surface = lease?.ports?.surface;
    if (!Number.isInteger(surface) || surface < 15290 || surface > 15309 || surface === 5290) {
      await stopChild(child);
      throw new Error("verification lease did not include a surface origin in 15290-15309");
    }
  }
  return { child, lease, leasePath, appFacingPath };
};

const startGateway = async (runDir, port) => {
  const readyPath = join(runDir, "gateway-ready.json");
  const child = remember(Bun.spawn(["bun", "integration/local-test-gateway.mjs"], {
    cwd: ROOT,
    env: {
      ...process.env,
      OMI_LOCAL_TEST_GATEWAY_PORT: String(port),
      OMI_LOCAL_TEST_GATEWAY_TOKEN: GATEWAY_TOKEN,
      OMI_LOCAL_TEST_GATEWAY_READY: readyPath,
    },
    stdout: "ignore",
    stderr: "pipe",
  }));
  const url = `http://127.0.0.1:${port}`;
  log(`  gateway listening ${url}`);
  const ok = await waitUntil(() => existsSync(readyPath) && curlReady(url, false), 8000, 20);
  if (!ok) {
    await stopChild(child);
    const stderr = await readStderr(child);
    throw new Error(`canned gateway did not become ready on ${url}. ${stderr}`);
  }
  return { child, url };
};

const startService = (options) => {
  const child = remember(Bun.spawn([
    "bun",
    "apps/service/bin/dev-server.ts",
    "--app-facing-test-lease",
    options.appFacingPath,
  ], {
    cwd: ROOT,
    env: {
      ...process.env,
      OMI_PORT: String(options.port),
      OMI_QA_DB: options.databasePath,
      OMI_SEED_PERSONA: "demo",
      OMI_RUN_ID: options.runId,
      OMI_DEV_READY_RECORD: options.readinessPath,
      OMI_LLM_GATEWAY_URL: options.gatewayUrl,
      OMI_LLM_GATEWAY_SERVICE_TOKEN: GATEWAY_TOKEN,
      OMI_STT_ENGINE: "",
      OMI_STT_MODEL: "",
      OMI_STT_VENV: "",
      TZ: "UTC",
    },
    stdout: "ignore",
    stderr: "pipe",
  }));
  return { child, startedAt: Date.now() };
};

const waitServiceReady = async (baseUrl, startedAt, timeoutMs = 20000) => {
  const ok = await waitUntil(() => curlReady(baseUrl, true), timeoutMs, 5);
  return { ok, ms: Date.now() - startedAt };
};

const readToken = (readinessPath) => {
  const ready = JSON.parse(readFileSync(readinessPath, "utf8"));
  if (typeof ready.devToken !== "string" || ready.devToken.length === 0) {
    throw new Error("readiness record had no dev token");
  }
  return ready.devToken;
};

const log = (message) => {
  process.stderr.write(`${message}\n`);
};

const measureBoot = async () => {
  const runId = `perf-boot-${Date.now()}`;
  const runDir = mkdtempSync(join(tmpdir(), "omi-perf-boot-"));
  const databasePath = join(runDir, "service.sqlite");
  log("  acquiring lease…");
  const held = await holdLease(runDir, runId, "service,gateway");
  log(`  lease service=${held.lease.ports.service} gateway=${held.lease.ports.gateway}`);
  const gateway = await startGateway(runDir, held.lease.ports.gateway);
  log("  canned gateway ready");
  const baseUrl = held.lease.urls.service;
  const cold = [];
  const warm = [];
  try {
    for (let i = 0; i < N; i += 1) {
      rmSync(databasePath, { force: true });
      const readinessPath = join(runDir, `ready-cold-${i}.json`);
      rmSync(readinessPath, { force: true });
      const spawned = startService({
        appFacingPath: held.appFacingPath,
        port: held.lease.ports.service,
        databasePath,
        runId,
        readinessPath,
        gatewayUrl: gateway.url,
      });
      const result = await waitServiceReady(baseUrl, spawned.startedAt);
      if (!result.ok) {
        await stopChild(spawned.child);
        const stderr = await readStderr(spawned.child);
        throw new Error(`cold boot ${i + 1} never reached /ready. ${stderr.slice(-2000)}`);
      }
      cold.push(result.ms);
      log(`  boot cold ${i + 1}/${N} ${result.ms}ms`);
      await stopChild(spawned.child);
      if (!existsSync(databasePath)) {
        throw new Error("cold boot did not leave a SQLite file for the warm measurement");
      }

      const warmReady = join(runDir, `ready-warm-${i}.json`);
      rmSync(warmReady, { force: true });
      const warmed = startService({
        appFacingPath: held.appFacingPath,
        port: held.lease.ports.service,
        databasePath,
        runId,
        readinessPath: warmReady,
        gatewayUrl: gateway.url,
      });
      const warmResult = await waitServiceReady(baseUrl, warmed.startedAt);
      if (!warmResult.ok) {
        await stopChild(warmed.child);
        const stderr = await readStderr(warmed.child);
        throw new Error(`warm boot ${i + 1} never reached /ready. ${stderr.slice(-2000)}`);
      }
      warm.push(warmResult.ms);
      log(`  boot warm ${i + 1}/${N} ${warmResult.ms}ms`);
      await stopChild(warmed.child);
    }
  } finally {
    await stopChild(gateway.child);
    await stopChild(held.child);
    rmSync(runDir, { recursive: true, force: true });
  }
  return {
    method: [
      "Spawn `bun apps/service/bin/dev-server.ts --app-facing-test-lease <lease>` with OMI_SEED_PERSONA=demo on a leased app-facing port.",
      "Clock starts immediately before spawn. Clock stops when GET /ready returns JSON `{status:\"ready\"}` (5ms poll).",
      "Canned gateway is already listening on its leased port before the service clock starts, so gateway process start is not included.",
      "Cold: OMI_QA_DB path does not exist. Warm: same file from the preceding cold boot, process killed and respawned. Warm skips reseed when settings already exist (persistentQaStores).",
    ].join(" "),
    cold: stats(cold),
    warm: stats(warm),
  };
};

const parseBunTestMs = (text) => {
  const matches = [...String(text).matchAll(/\[([0-9.]+)\s*ms\]/g)];
  if (matches.length === 0) return null;
  return Number(matches[matches.length - 1][1]);
};

const measureFormation = async () => {
  const bunReported = [];
  const wall = [];
  const filter = "wired: the transcript fact is in synthesized memory text";
  for (let i = 0; i < N; i += 1) {
    const started = Date.now();
    const result = spawnSync("bun", [
      "test",
      "apps/service/routes/stm-notes.round-trip.test.ts",
      "-t",
      filter,
    ], {
      cwd: ROOT,
      encoding: "utf8",
      env: { ...process.env },
    });
    const elapsed = Date.now() - started;
    wall.push(elapsed);
    const parsed = parseBunTestMs(`${result.stdout}\n${result.stderr}`);
    if (parsed !== null) bunReported.push(parsed);
    if (result.status !== 0) {
      throw new Error(`formation test failed on run ${i + 1}: ${result.stderr.slice(-1500)}`);
    }
    log(`  formation ${i + 1}/${N} bun=${parsed ?? "unparsed"}ms wall=${elapsed}ms`);
  }
  return {
    method: [
      "Existing seam: `bun test apps/service/routes/stm-notes.round-trip.test.ts -t \"wired: the transcript fact is in synthesized memory text\"`.",
      "That test finalizes a scripted listen conversation and asserts GET /v1/memories contains the transcript fact.",
      "bunReported is the duration bun prints on the passing test. wall is spawn-to-exit of that bun test process (includes bun startup and in-process service boot).",
    ].join(" "),
    bunReported: stats(bunReported),
    wall: stats(wall),
  };
};

const streamChatTurn = async (baseUrl, token, id) => {
  const t0 = Date.now();
  const admitted = await fetch(`${baseUrl}/v1/chat-messages`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "x-omi-client-id": "perf-baseline::macos",
    },
    body: JSON.stringify({
      op: "create",
      opId: `op-${id}`,
      id,
      at: 1_786_352_400_000 + Math.floor(Math.random() * 1000),
      text: "perf-baseline ping",
      sender: "human",
      journalRevision: 1,
      type: "text",
      appId: null,
      chatSessionId: null,
      messageSource: "desktop_chat",
      metadata: null,
      attachmentIds: [],
    }),
  });
  const admissionMs = Date.now() - t0;
  if (admitted.status !== 201) {
    throw new Error(`chat admission status ${admitted.status}: ${await admitted.text()}`);
  }
  const body = await admitted.json();
  const generationId = body?.generation?.id;
  if (typeof generationId !== "string" || generationId.length === 0) {
    throw new Error("chat admission returned no generation id");
  }
  const events = await fetch(`${baseUrl}/v1/chat-generations/${generationId}/events`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!events.ok || !events.body) {
    throw new Error(`chat events status ${events.status}`);
  }
  const reader = events.body.getReader();
  const decoder = new TextDecoder();
  let text = "";
  let firstTokenMs = null;
  let fullTurnMs = null;
  for (;;) {
    const chunk = await reader.read();
    if (chunk.done) break;
    text += decoder.decode(chunk.value, { stream: true });
    if (firstTokenMs === null && /(?:^|\n)event: delta\n/.test(text)) {
      firstTokenMs = Date.now() - t0;
    }
    if (/(?:^|\n)event: done\n/.test(text)) {
      fullTurnMs = Date.now() - t0;
      break;
    }
  }
  if (firstTokenMs === null || fullTurnMs === null) {
    throw new Error(`chat stream missed delta/done. body=${text.slice(0, 400)}`);
  }
  return { admissionMs, firstTokenMs, fullTurnMs };
};

const measureChat = async () => {
  const runId = `perf-chat-${Date.now()}`;
  const runDir = mkdtempSync(join(tmpdir(), "omi-perf-chat-"));
  const databasePath = join(runDir, "service.sqlite");
  const readinessPath = join(runDir, "ready.json");
  const held = await holdLease(runDir, runId, "service,gateway");
  const gateway = await startGateway(runDir, held.lease.ports.gateway);
  const spawned = startService({
    appFacingPath: held.appFacingPath,
    port: held.lease.ports.service,
    databasePath,
    runId,
    readinessPath,
    gatewayUrl: gateway.url,
  });
  const first = [];
  const rest = [];
  try {
    const ready = await waitServiceReady(held.lease.urls.service, spawned.startedAt, 20000);
    if (!ready.ok) throw new Error("chat stack service never reached /ready");
    const token = readToken(readinessPath);
    for (let i = 0; i < N; i += 1) {
      const turn = await streamChatTurn(held.lease.urls.service, token, `perf-chat-${i}-${Date.now()}`);
      if (i === 0) first.push(turn);
      else rest.push(turn);
      log(`  chat ${i + 1}/${N} admit=${turn.admissionMs}ms first-token=${turn.firstTokenMs}ms full=${turn.fullTurnMs}ms`);
    }
  } finally {
    await stopChild(spawned.child);
    await stopChild(gateway.child);
    await stopChild(held.child);
    rmSync(runDir, { recursive: true, force: true });
  }
  const all = [...first, ...rest];
  return {
    method: [
      "Leased service + canned gateway. Demo persona. POST /v1/chat-messages then GET /v1/chat-generations/:id/events.",
      "Clock starts at POST. first-token is first SSE `event: delta`. full-turn is first SSE `event: done`.",
      "Run 1 is reported separately as the first turn after boot; runs 2..N are subsequent turns on the same process. Primary table uses all N.",
    ].join(" "),
    firstTurn: first[0] ?? null,
    admission: stats(all.map((row) => row.admissionMs)),
    firstToken: stats(all.map((row) => row.firstTokenMs)),
    fullTurn: stats(all.map((row) => row.fullTurnMs)),
    subsequentFirstToken: stats(rest.map((row) => row.firstTokenMs)),
    subsequentFullTurn: stats(rest.map((row) => row.fullTurnMs)),
  };
};

const surfaceProbeJs = (route, wantReady) => `(function(){
  var expected = ${JSON.stringify(route)};
  var wantReady = ${wantReady ? "true" : "false"};
  var root = document.querySelector("main[data-production-shell='true']");
  if (!root) return ${JSON.stringify(PENDING)};
  var current = root.getAttribute("data-route") || "";
  var rewindAlias = expected === "rewind" && current === "screen";
  if (expected && current !== expected && !rewindAlias) return ${JSON.stringify(PENDING)};
  var state = root.getAttribute("data-surface-state") || "";
  var text = String(root.innerText || root.textContent || "").replace(/\\s+/g, " ").trim();
  if (text.length === 0) return ${JSON.stringify(PENDING)};
  if (wantReady) {
    if (state === "initial-loading" || state === "refreshing") return ${JSON.stringify(PENDING)};
  }
  var nav = performance.getEntriesByType("navigation")[0];
  var paints = performance.getEntriesByType("paint");
  var fcp = null;
  for (var i = 0; i < paints.length; i++) {
    if (paints[i].name === "first-contentful-paint") fcp = Math.round(paints[i].startTime);
  }
  return JSON.stringify({
    schema: "omi.perf-probe.v1",
    route: current,
    state: state,
    t: Math.round(performance.now()),
    fcp: fcp,
    navMs: nav ? Math.round(nav.duration) : null
  });
})()`;

const parseProbe = (text) => {
  const lines = String(text ?? "").split(/\r?\n/);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const match = lines[i].match(/^PROBE_JS: (.*) error: (.*)$/);
    if (!match) continue;
    const value = match[1];
    const error = match[2];
    if (error !== "none") return { ok: false, reason: `probe-js-error:${error}`, raw: lines[i] };
    if (value === PENDING || value === "nil") return { ok: false, reason: "probe-timeout", raw: lines[i] };
    try {
      return { ok: true, payload: JSON.parse(value), raw: lines[i] };
    } catch {
      return { ok: false, reason: "probe-json", raw: lines[i] };
    }
  }
  return { ok: false, reason: "probe-missing", raw: null };
};

const launchSurface = ({
  serviceUrl,
  token,
  surfacePort,
  buildDir,
  route,
  wantReady,
}) => {
  const launcher = join(ROOT, "frontend/shells/macos/scripts/dev-run-macos.sh");
  const started = Date.now();
  const result = spawnSync(launcher, ["--api", serviceUrl, "--route", route], {
    cwd: dirname(launcher),
    env: {
      ...process.env,
      OMI_API_TOKEN: token,
      OMI_API_BASE_URL: serviceUrl,
      OMI_SURFACE_PORT: String(surfacePort),
      OMI_APP_NAME: "omi-on-perf-baseline",
      OMI_BUILD_DIR: buildDir,
      OMI_PROBE_JS: surfaceProbeJs(route, wantReady),
      OMI_PROBE_EXIT: "1",
      OMI_PROBE_PENDING_VALUE: PENDING,
      OMI_PROBE_MAX_ATTEMPTS: "100",
      OMI_PROBE_RETRY_INTERVAL: "0.05",
      OMI_PROBE_DELAY: "0.05",
      OMI_PROBE_SETTLE: "0.05",
      OMI_ACCEPTANCE_WAIT_SECONDS: "45",
      OMI_READY_TIMEOUT_SECONDS: "30",
    },
    encoding: "utf8",
  });
  const elapsedMs = Date.now() - started;
  let logText = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  const runLog = join(buildDir, "omi-on-perf-baseline.run.log");
  try {
    logText += `\n${readFileSync(runLog, "utf8")}`;
  } catch {
    // probe often lives only on the run log
  }
  if (/api\.omi\.me|\?rig=dev/.test(logText)) {
    throw new Error("UI launch observed a production origin or ?rig=dev. Stopping.");
  }
  return { elapsedMs, probe: parseProbe(logText), status: result.status, logText };
};

const walkProbeJs = () => {
  const routes = JSON.stringify(CONTROL_NAV_ROUTES);
  return `(function(){
  var ROUTES = ${routes};
  var KEY = "omi.perf-walk.v1";
  var PENDING = ${JSON.stringify(PENDING)};
  var PALETTE_LABEL = {
    home: "Home", conversations: "Conversations", memories: "Memories",
    folders: "Folders", tasks: "Tasks", rewind: "Rewind", apps: "Apps",
    "brain-map": "Brain Map", chat: "Chat", settings: "Settings", listen: "Listen"
  };
  var load = function() {
    try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  };
  var state = load() || { i: 0, clicked: false, samples: [], t0: Date.now() };
  var root = document.querySelector("main[data-production-shell='true']");
  var save = function() { sessionStorage.setItem(KEY, JSON.stringify(state)); };
  var onRoute = function(route, current) {
    if (route === "rewind") return current === "rewind" || current === "screen";
    return current === route;
  };
  var navLink = function(route) {
    var nodes = document.querySelectorAll("a[href]");
    for (var i = 0; i < nodes.length; i++) {
      var href = nodes[i].getAttribute("href") || "";
      if (href.indexOf("route=" + route) !== -1 && !nodes[i].closest(".command-palette")) return nodes[i];
    }
    return null;
  };
  var paletteButton = function(label) {
    var buttons = document.querySelectorAll(".command-palette-list button");
    for (var i = 0; i < buttons.length; i++) {
      var text = String(buttons[i].textContent || "").replace(/\\s+/g, " ").trim();
      if (text === label || text.indexOf(label) === 0) return buttons[i];
    }
    return null;
  };
  if (!root) { save(); return PENDING; }
  var current = root.getAttribute("data-route") || "";
  var text = String(root.innerText || root.textContent || "").replace(/\\s+/g, " ").trim();
  var phase = root.getAttribute("data-surface-state") || "";
  var loading = phase === "initial-loading" || phase === "refreshing";
  var route = ROUTES[state.i];
  if (!route) {
    return JSON.stringify({ schema: "omi.perf-walk.v1", samples: state.samples, t: Date.now() - state.t0 });
  }
  if (onRoute(route, current) && text.length > 0 && !loading) {
    if (state.samples.length === state.i) {
      state.samples.push({
        route: route,
        renderedRoute: current,
        state: phase,
        t: Date.now() - state.t0,
        fromClick: state.clickedAt ? Date.now() - state.clickedAt : null
      });
    }
    state.i += 1;
    state.clicked = false;
    state.clickedAt = null;
    save();
    return PENDING;
  }
  if (!state.clicked) {
    var link = navLink(route);
    if (link) {
      state.clicked = true;
      state.clickedAt = Date.now();
      save();
      link.click();
      return PENDING;
    }
    var palette = document.querySelector(".command-palette");
    if (!palette) {
      var trigger = document.querySelector(".command-discovery-trigger");
      if (trigger) { trigger.click(); save(); return PENDING; }
    } else {
      var button = paletteButton(PALETTE_LABEL[route] || route);
      if (button && !button.disabled) {
        state.clicked = true;
        state.clickedAt = Date.now();
        save();
        button.click();
        return PENDING;
      }
    }
  }
  save();
  return PENDING;
})()`;
};

const launchWalk = ({ serviceUrl, token, surfacePort, buildDir }) => {
  const launcher = join(ROOT, "frontend/shells/macos/scripts/dev-run-macos.sh");
  const started = Date.now();
  const result = spawnSync(launcher, ["--api", serviceUrl, "--route", "home"], {
    cwd: dirname(launcher),
    env: {
      ...process.env,
      OMI_API_TOKEN: token,
      OMI_API_BASE_URL: serviceUrl,
      OMI_SURFACE_PORT: String(surfacePort),
      OMI_APP_NAME: "omi-on-perf-baseline",
      OMI_BUILD_DIR: buildDir,
      OMI_PROBE_JS: walkProbeJs(),
      OMI_PROBE_EXIT: "1",
      OMI_PROBE_PENDING_VALUE: PENDING,
      OMI_PROBE_MAX_ATTEMPTS: "100",
      // Swift caps attempts at 100. 50ms matches the dedicated-launch grain so
      // fromClick is not quantized to 400ms. 100×50ms = 5s of probing after the
      // 2s delay; that is enough when palette fallback can actually click.
      OMI_PROBE_RETRY_INTERVAL: "0.05",
      OMI_PROBE_DELAY: "2",
      OMI_PROBE_SETTLE: "0.05",
      OMI_ACCEPTANCE_WAIT_SECONDS: "180",
      OMI_READY_TIMEOUT_SECONDS: "30",
    },
    encoding: "utf8",
  });
  const elapsedMs = Date.now() - started;
  let logText = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  try {
    logText += `\n${readFileSync(join(buildDir, "omi-on-perf-baseline.run.log"), "utf8")}`;
  } catch {
    // ignore
  }
  if (/api\.omi\.me|\?rig=dev/.test(logText)) {
    throw new Error("UI walk observed a production origin or ?rig=dev. Stopping.");
  }
  return { elapsedMs, probe: parseProbe(logText), status: result.status, logText };
};

const measureUi = async ({ walksOnly = false } = {}) => {
  const runId = `perf-ui-${Date.now()}`;
  const runDir = mkdtempSync(join(tmpdir(), "omi-perf-ui-"));
  const stackDir = join(runDir, "stack");
  mkdirSync(stackDir);
  const buildDir = join(runDir, "build");
  mkdirSync(buildDir);
  log("  booting leased demo stack for UI…");
  const up = spawnSync("bash", ["integration/dev-stack.sh", "--up", "--lease"], {
    cwd: ROOT,
    env: { ...process.env, OMI_SEED_PERSONA: "demo", OMI_DEV_STACK_RUNDIR: stackDir },
    encoding: "utf8",
  });
  if (up.status !== 0) {
    throw new Error(`could not boot leased stack for UI.\n${up.stderr}\n${up.stdout}`);
  }
  const stopStack = () => {
    spawnSync("bash", ["integration/dev-stack.sh", "--stop"], {
      cwd: ROOT,
      env: { ...process.env, OMI_DEV_STACK_RUNDIR: stackDir },
      encoding: "utf8",
    });
  };
  try {
    const owner = JSON.parse(readFileSync(join(stackDir, "service-owner.json"), "utf8"));
    const ready = JSON.parse(readFileSync(owner.readinessPath, "utf8"));
    const lease = JSON.parse(readFileSync(join(stackDir, "port-lease.json"), "utf8"));
    const token = ready.devToken;
    const serviceUrl = lease.urls.service;
    const surfacePort = lease.ports.surface;
    if (serviceUrl.includes("api.omi.me")) throw new Error("refusing a production origin");

    const compile = launchSurface({
      serviceUrl, token, surfacePort, buildDir, route: "home", wantReady: true,
    });
    log(`  ui compile+first-home launcher=${compile.elapsedMs}ms probe=${compile.probe.ok ? compile.probe.payload.t : compile.probe.reason}`);

    const firstRender = [];
    const perSurface = {};
    if (!walksOnly) {
    for (let i = 0; i < N; i += 1) {
      const launched = launchSurface({
        serviceUrl, token, surfacePort, buildDir, route: "home", wantReady: true,
      });
      if (!launched.probe.ok) {
        throw new Error(`home first-render ${i + 1} failed: ${launched.probe.reason}\n${launched.logText.slice(-1500)}`);
      }
      firstRender.push({
        launcherMs: launched.elapsedMs,
        pageMs: launched.probe.payload.t,
        fcp: launched.probe.payload.fcp,
        state: launched.probe.payload.state,
      });
      log(`  first-render ${i + 1}/${N} launcher=${launched.elapsedMs}ms page=${launched.probe.payload.t}ms state=${launched.probe.payload.state}`);
    }

    for (const route of LAUNCHER_ROUTES) {
      const samples = [];
      for (let i = 0; i < N; i += 1) {
        const launched = launchSurface({
          serviceUrl, token, surfacePort, buildDir, route, wantReady: true,
        });
        if (!launched.probe.ok) {
          throw new Error(`${route} first-render ${i + 1} failed: ${launched.probe.reason}\n${launched.logText.slice(-1500)}`);
        }
        samples.push({
          launcherMs: launched.elapsedMs,
          pageMs: launched.probe.payload.t,
          fcp: launched.probe.payload.fcp,
          state: launched.probe.payload.state,
          renderedRoute: launched.probe.payload.route,
        });
        log(`  surface ${route} ${i + 1}/${N} launcher=${launched.elapsedMs}ms page=${launched.probe.payload.t}ms state=${launched.probe.payload.state}`);
      }
      perSurface[route] = {
        how: "dedicated --route launch; clock is launcher spawn to probe reporting that route past initial-loading/refreshing",
        launcher: stats(samples.map((row) => row.launcherMs)),
        page: stats(samples.map((row) => row.pageMs)),
        states: samples.map((row) => row.state),
      };
    }
    }

    const walks = [];
    for (let i = 0; i < N; i += 1) {
      const launched = launchWalk({ serviceUrl, token, surfacePort, buildDir });
      if (!launched.probe.ok) {
        log(`  walk ${i + 1}/${N} failed: ${launched.probe.reason}`);
        walks.push({ ok: false, reason: launched.probe.reason, launcherMs: launched.elapsedMs });
        continue;
      }
      walks.push({
        ok: true,
        launcherMs: launched.elapsedMs,
        samples: launched.probe.payload.samples,
      });
      log(`  walk ${i + 1}/${N} launcher=${launched.elapsedMs}ms routes=${(launched.probe.payload.samples || []).length}`);
    }
    const walkByRoute = {};
    for (const route of [...WALK_ONLY_ROUTES, ...CONTROL_NAV_ROUTES]) {
      const clickSamples = [];
      for (const walk of walks) {
        if (!walk.ok) continue;
        const sample = (walk.samples || []).find((row) => row.route === route);
        if (sample && typeof sample.fromClick === "number") clickSamples.push(sample.fromClick);
      }
      if (WALK_ONLY_ROUTES.includes(route) || clickSamples.length > 0) {
        walkByRoute[route] = {
          how: "in-app click from the control-harness NAV_ROUTES walk; fromClick is click to data-ready",
          fromClick: stats(clickSamples),
        };
      }
    }

    return {
      method: [
        "Leased demo stack (`integration/dev-stack.sh --up --lease`, OMI_SEED_PERSONA=demo) and leased surface origin in 15290-15309.",
        "macOS probe hook (OMI_PROBE_JS) with 50ms delay, 50ms retry, pending until main[data-production-shell] matches the route and data-surface-state is not initial-loading/refreshing.",
        "App first render and per-launcher-route: spawn frontend/shells/macos/scripts/dev-run-macos.sh --route <name>. Clock is launcher start to successful probe.",
        "pageMs is performance.now() inside the page (navigation-start relative). launcherMs includes Swift rebuild of an already-built bundle plus process spawn.",
        "First launch after creating the build dir is reported separately as compile-included and is not in the N=5 first-render set.",
        "Walks use the same NAV_ROUTES list as integration/control-acceptance/driver.js, 2s initial probe delay, 50ms retry (Swift caps attempts at 100).",
        "fromClick is wall-clock from click to the next probe that sees data-ready; values clustered at ~50ms are at the probe grain, not a claimed 50ms render.",
        "rewind/apps/brain-map cannot be opened with --route (launcher whitelist). Those three have no dedicated landing-page number; in-app fromClick is the measurement.",
      ].join(" "),
      compileIncludedHome: {
        launcherMs: compile.elapsedMs,
        probe: compile.probe.ok ? compile.probe.payload : { reason: compile.probe.reason },
      },
      firstRender: {
        launcher: stats(firstRender.map((row) => row.launcherMs)),
        page: stats(firstRender.map((row) => row.pageMs)),
        fcp: stats(firstRender.map((row) => row.fcp).filter((value) => typeof value === "number")),
        states: firstRender.map((row) => row.state),
      },
      perSurface,
      walkOnlyRoutes: walkByRoute,
      walksFailed: walks.filter((walk) => !walk.ok).length,
    };
  } finally {
    stopStack();
    rmSync(runDir, { recursive: true, force: true });
  }
};

const parseLaneDuration = (text) => {
  const match = String(text).match(/\b(PASS|FAIL) in (\d+)ms/);
  if (!match) return null;
  return { result: match[1].toLowerCase(), durationMs: Number(match[2]) };
};

const measureLanes = async () => {
  const results = {};
  for (const lane of laneIds) {
    const samples = [];
    for (let i = 0; i < N; i += 1) {
      log(`  ${lane} ${i + 1}/${N} starting…`);
      const started = Date.now();
      const result = spawnSync("node", ["integration/lanes.mjs", lane], {
        cwd: ROOT,
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
        env: { ...process.env },
      });
      const wall = Date.now() - started;
      const parsed = parseLaneDuration(`${result.stdout}\n${result.stderr}`)
        ?? { result: result.status === 0 ? "pass" : "fail", durationMs: wall };
      samples.push({ ...parsed, wallMs: wall, status: result.status });
      log(`  ${lane} ${i + 1}/${N} ${parsed.result} runner=${parsed.durationMs}ms wall=${wall}ms`);
      if (result.status !== 0) {
        const combined = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
        log(`  ${lane} ${i + 1}/${N} fail tail:\n${combined.slice(-2500)}`);
      }
    }
    results[lane] = {
      method: `node integration/lanes.mjs ${lane}; duration is the runner's printed wall-clock, which includes preflight.`,
      runner: stats(samples.map((row) => row.durationMs)),
      wall: stats(samples.map((row) => row.wallMs)),
      outcomes: samples.map((row) => row.result),
    };
  }
  return results;
};

const main = async () => {
  const machine = captureMachine();
  log(`perf-baseline ref=${machine.refShort} load=${machine.loadavg.join("/")} davidPorts=${JSON.stringify(machine.listeners)} n=${N}`);
  const report = {
    schema: "omi.performance-baseline.v1",
    n: N,
    machine,
    measurements: {},
  };
  if (only.has("boot")) {
    log("measuring service boot…");
    report.measurements.boot = await measureBoot();
  }
  if (only.has("formation")) {
    log("measuring formation latency…");
    report.measurements.formation = await measureFormation();
  }
  if (only.has("chat")) {
    log("measuring chat first-token / full-turn…");
    report.measurements.chat = await measureChat();
  }
  if (only.has("ui") || only.has("walk")) {
    log("measuring app / per-surface first render…");
    report.measurements.ui = await measureUi({ walksOnly: only.has("walk") && !only.has("ui") });
  }
  if (only.has("lanes")) {
    log("measuring lane wall-clock…");
    report.measurements.lanes = await measureLanes();
  }
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
};

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exit(1);
});
