import { spawn, spawnSync } from "node:child_process";
import { createConnection } from "node:net";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

import { generateManifest, packageRoot, viteOrigin, withLabPreview } from "./ui-harness-catalog.mjs";
import {
  assertCaptureSummary,
  CAPTURE_SUMMARY_SCHEMA,
  decodePngFile,
  DIFF_METHOD,
  DIFF_SUMMARY_SCHEMA,
  pixelDelta,
  sideBySidePng,
} from "./ui-harness-png.mjs";

const frontendRoot = resolve(packageRoot, "../..");
const defaultOutRoot = join(packageRoot, ".build", "ui-harness");
const chromeCandidates = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
].filter(Boolean);

function pageUrl(origin, path) {
  return new URL(path, `${origin}/`).href;
}

function json(value) {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function nowIso() {
  return new Date().toISOString();
}

function runStamp() {
  return nowIso().replaceAll(":", "").replaceAll(".", "-");
}

export function defaultRunDir(mode, stamp = runStamp()) {
  return join(defaultOutRoot, `${mode}-${stamp}`);
}

function chromePath() {
  const found = chromeCandidates.find((candidate) => existsSync(candidate));
  if (!found) throw new Error("Chrome/Chromium is not installed; set CHROME_PATH");
  return found;
}

function waitForFile(file, timeoutMs) {
  const started = Date.now();
  return new Promise((resolveWait, reject) => {
    const tick = () => {
      if (existsSync(file) && readFileSync(file, "utf8").trim().length > 0) {
        resolveWait(file);
        return;
      }
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`timed out waiting for ${file}`));
        return;
      }
      setTimeout(tick, 50);
    };
    tick();
  });
}

class Cdp {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 0;
    this.pending = new Map();
    this.handlers = new Map();
    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id != null && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message ?? JSON.stringify(message.error)));
        else resolve(message.result);
        return;
      }
      if (message.method) {
        const key = message.sessionId ? `${message.sessionId}:${message.method}` : message.method;
        for (const [pattern, handlers] of this.handlers) {
          if (pattern === message.method || pattern === key) {
            for (const handler of handlers) handler(message.params ?? {}, message);
          }
        }
      }
    });
  }

  on(method, handler) {
    const list = this.handlers.get(method) ?? [];
    list.push(handler);
    this.handlers.set(method, list);
    return () => {
      const next = (this.handlers.get(method) ?? []).filter((item) => item !== handler);
      if (next.length === 0) this.handlers.delete(method);
      else this.handlers.set(method, next);
    };
  }

  send(method, params = {}, sessionId) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify(sessionId ? { id, method, params, sessionId } : { id, method, params }));
    });
  }

  close() {
    this.ws.close();
  }
}

async function connectCdp(url) {
  const ws = new WebSocket(url);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", () => reject(new Error(`CDP websocket failed: ${url}`)), { once: true });
  });
  return new Cdp(ws);
}

async function launchChrome() {
  const userDataDir = mkdtempSync(join(tmpdir(), "omi-ui-harness-chrome-"));
  const chrome = spawn(chromePath(), [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--mute-audio",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-default-apps",
    "--disable-popup-blocking",
    "--disable-translate",
    "--force-color-profile=srgb",
    "--font-render-hinting=none",
    "--disable-lcd-text",
    "--disable-dev-shm-usage",
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=0",
    `--user-data-dir=${userDataDir}`,
    "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });
  const activePort = join(userDataDir, "DevToolsActivePort");
  try {
    await waitForFile(activePort, 15_000);
    const [port, path] = readFileSync(activePort, "utf8").trim().split("\n");
    const browserUrl = `ws://127.0.0.1:${port}${path}`;
    const cdp = await connectCdp(browserUrl);
    return {
      cdp,
      userDataDir,
      async close() {
        cdp.close();
        chrome.kill("SIGKILL");
        await delay(50);
        rmSync(userDataDir, { recursive: true, force: true });
      },
    };
  } catch (error) {
    chrome.kill("SIGKILL");
    rmSync(userDataDir, { recursive: true, force: true });
    throw error;
  }
}

async function attachPage(cdp) {
  const created = await cdp.send("Target.createTarget", { url: "about:blank" });
  const attached = await cdp.send("Target.attachToTarget", { targetId: created.targetId, flatten: true });
  const sessionId = attached.sessionId;
  const send = (method, params) => cdp.send(method, params, sessionId);
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  return { sessionId, send };
}

function consoleText(params) {
  const args = params.args ?? [];
  return args.map((arg) => arg.value ?? arg.description ?? arg.type ?? "").join(" ").trim();
}

async function captureBrowserEntry(page, origin, entry) {
  const errors = [];
  const onConsole = (params) => {
    if (params.type === "error") errors.push(consoleText(params));
  };
  const onException = (params) => {
    errors.push(params.exceptionDetails?.text ?? params.exceptionDetails?.exception?.description ?? "exception");
  };
  const offConsole = page.cdp.on(`${page.sessionId}:Runtime.consoleAPICalled`, onConsole);
  const offException = page.cdp.on(`${page.sessionId}:Runtime.exceptionThrown`, onException);
  const started = Date.now();
  try {
    await page.send("Emulation.setDeviceMetricsOverride", {
      width: entry.viewport.width,
      height: entry.viewport.height,
      deviceScaleFactor: 1,
      mobile: entry.platform === "mobile",
    });
    await page.send("Emulation.setEmulatedMedia", {
      features: [
        { name: "prefers-reduced-motion", value: "reduce" },
        { name: "prefers-color-scheme", value: entry.platform === "mobile" ? "dark" : "light" },
      ],
    });
    const readyWait = new Promise((resolve) => {
      const off = page.cdp.on(`${page.sessionId}:Runtime.consoleAPICalled`, (params) => {
        if (String(consoleText(params)).includes("OMI_PRODUCTION_READY")) {
          off();
          resolve(true);
        }
      });
    });
    await page.send("Page.navigate", { url: pageUrl(origin, entry.path) });
    const ready = await Promise.race([readyWait, delay(12_000).then(() => false)]);
    if (!ready) errors.push("OMI_PRODUCTION_READY timed out");
    await page.send("Runtime.evaluate", {
      expression: "document.fonts.ready.then(() => true)",
      awaitPromise: true,
    });
    await page.send("Runtime.evaluate", {
      expression: `(() => {
        const style = document.createElement("style");
        style.textContent = "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important;}";
        document.documentElement.appendChild(style);
        return document.fonts.status;
      })()`,
    });
    await page.send("Runtime.evaluate", {
      expression: "new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))",
      awaitPromise: true,
    });
    await delay(120);
    const screenshot = await page.send("Page.captureScreenshot", { format: "png", fromSurface: true });
    return {
      png: Buffer.from(screenshot.data, "base64"),
      renderMs: Date.now() - started,
      consoleErrors: [...new Set(errors.filter(Boolean))],
    };
  } finally {
    offConsole();
    offException();
  }
}

function writeCaptureSummary(outDir, summary) {
  const file = join(outDir, "summary.json");
  writeFileSync(file, json(summary));
  return file;
}

function selectStates(manifest, { id, limit } = {}) {
  let states = manifest.states;
  if (id) {
    states = states.filter((entry) => entry.id === id || entry.id.startsWith(`${id}.`));
    if (states.length === 0) throw new Error(`no manifest entry matches --id ${id}`);
  }
  if (limit != null) states = states.slice(0, limit);
  return states;
}

export async function captureBrowser({ outDir, id, limit } = {}) {
  const distMarker = resolve(packageRoot, "../i18n/dist/index.js");
  if (!existsSync(distMarker)) {
    throw new Error("workspace packages are not built; run: cd frontend && pnpm -r build");
  }
  const dest = outDir ? resolve(outDir) : defaultRunDir("browser");
  mkdirSync(dest, { recursive: true });
  const startedAt = nowIso();
  const startedMs = Date.now();
  return withLabPreview(async (server) => {
    const origin = viteOrigin(server);
    const manifest = generateManifest(origin);
    writeFileSync(join(dest, "manifest.json"), json(manifest));
    const states = selectStates(manifest, { id, limit });
    const chrome = await launchChrome();
    try {
      const session = await attachPage(chrome.cdp);
      const page = { cdp: chrome.cdp, sessionId: session.sessionId, send: session.send };
      const entries = [];
      for (const entry of states) {
        const captured = await captureBrowserEntry(page, origin, entry);
        const file = join(dest, `${entry.id}.png`);
        writeFileSync(file, captured.png);
        entries.push({
          id: entry.id,
          url: pageUrl(origin, entry.path),
          bytes: captured.png.length,
          viewport: entry.viewport,
          renderMs: captured.renderMs,
          consoleErrors: captured.consoleErrors,
        });
        const errorMark = captured.consoleErrors.length > 0 ? ` errors=${captured.consoleErrors.length}` : "";
        process.stdout.write(`captured ${entry.id} ${captured.png.length}b ${captured.renderMs}ms${errorMark}\n`);
      }
      const summary = {
        schema: CAPTURE_SUMMARY_SCHEMA,
        mode: "browser",
        origin,
        outDir: dest,
        startedAt,
        finishedAt: nowIso(),
        wallClockMs: Date.now() - startedMs,
        count: entries.length,
        errorCount: entries.filter((entry) => entry.consoleErrors.length > 0).length,
        entries,
      };
      assertCaptureSummary(summary);
      writeCaptureSummary(dest, summary);
      return summary;
    } finally {
      await chrome.close();
    }
  });
}

function listeningCommand(port) {
  const result = spawnSync("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" });
  const line = (result.stdout ?? "").trim().split("\n")[1];
  if (!line) return null;
  return line.split(/\s+/)[0] ?? null;
}

function waitPortFree(port, timeoutMs = 10_000) {
  const started = Date.now();
  return new Promise((resolveWait, reject) => {
    const tick = () => {
      const socket = createConnection({ host: "127.0.0.1", port });
      socket.once("connect", () => {
        socket.destroy();
        if (Date.now() - started > timeoutMs) {
          reject(new Error(`port ${port} stayed busy`));
          return;
        }
        setTimeout(tick, 150);
      });
      socket.once("error", () => resolveWait());
    };
    tick();
  });
}

function cleanEnv(env) {
  return Object.fromEntries(Object.entries(env).filter(([, value]) => value != null && value !== ""));
}

function runCommand(command, args, env, timeoutMs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { env: cleanEnv(env), stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error(`timed out: ${command} ${args.join(" ")}`));
    }, timeoutMs);
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

function parseShellConsoleErrors(logText) {
  return [...new Set(
    logText
      .split("\n")
      .filter((line) => line.startsWith("WEBVIEW-CONSOLE: error "))
      .map((line) => line.slice("WEBVIEW-CONSOLE: error ".length).trim())
      .filter(Boolean),
  )];
}

export async function captureShell({ outDir, id, limit } = {}) {
  const dest = outDir ? resolve(outDir) : defaultRunDir("shell");
  mkdirSync(dest, { recursive: true });
  const startedAt = nowIso();
  const startedMs = Date.now();
  const dist = join(packageRoot, "dist");
  const appName = "omi-on-ui-harness";
  if (!existsSync(join(dist, "index.html"))) {
    throw new Error("surfaces dist missing; run pnpm --filter @omi-core/surfaces build");
  }
  const occupant = listeningCommand(5290);
  if (occupant && occupant !== appName) {
    throw new Error(`loopback 5290 is held by ${occupant}; shell capture needs exclusive origin http://127.0.0.1:5290`);
  }
  const manifest = await generateManifest("http://127.0.0.1:5290");
  writeFileSync(join(dest, "manifest.json"), json(manifest));
  const states = selectStates(manifest, { id, limit });
  const buildDir = join(frontendRoot, ".build", "ui-harness-shell");
  const launcher = join(frontendRoot, "shells/macos/scripts/build-shell.sh");
  const buildEnv = {
    PATH: process.env.PATH,
    TMPDIR: process.env.TMPDIR,
    LANG: process.env.LANG,
    HOME: process.env.HOME,
    DEVELOPER_DIR: process.env.DEVELOPER_DIR,
    SDKROOT: process.env.SDKROOT,
    OMI_BUILD_DIR: buildDir,
    OMI_APP_NAME: appName,
    OMI_SURFACES_DIST: dist,
    OMI_SURFACE_PORT: "5290",
  };
  const built = await runCommand("/bin/bash", [launcher], buildEnv, 180_000);
  if (built.code !== 0) throw new Error(`macOS shell build failed\n${built.stderr || built.stdout}`);
  const executable = join(buildDir, `${appName}.app`, "Contents/MacOS", appName);
  if (!existsSync(executable)) throw new Error(`shell executable missing at ${executable}`);
  const entries = [];
  const skipped = [];
  for (const entry of states) {
    if (!entry.shell.reachable) {
      skipped.push({ id: entry.id, reason: entry.shell.reason });
      entries.push({
        id: entry.id,
        url: entry.url,
        bytes: 0,
        viewport: entry.viewport,
        renderMs: 0,
        consoleErrors: [],
        skipped: true,
        skipReason: entry.shell.reason,
      });
      process.stdout.write(`skipped ${entry.id} ${entry.shell.reason}\n`);
      continue;
    }
    await waitPortFree(5290);
    const pngPath = join(dest, `${entry.id}.png`);
    rmSync(pngPath, { force: true });
    const query = entry.path.startsWith("?") ? entry.path.slice(1) : entry.path;
    const env = {
      ...buildEnv,
      OMI_SURFACE_QUERY: query,
      OMI_SNAPSHOT_PATH: pngPath,
      OMI_PROBE_EXIT: "1",
      OMI_NATIVE_VIEWPORT_WIDTH: String(entry.viewport.width),
      OMI_NATIVE_VIEWPORT_HEIGHT: String(entry.viewport.height),
      OMI_ACCEPTANCE_WAIT_SECONDS: "20",
    };
    delete env.OMI_API_BASE_URL;
    delete env.OMI_API_TOKEN;
    const capturedAt = Date.now();
    const result = await runCommand(executable, [], env, 40_000);
    const logText = `${result.stdout}\n${result.stderr}`;
    const consoleErrors = parseShellConsoleErrors(logText);
    if (!existsSync(pngPath)) {
      throw new Error(`shell capture produced no PNG for ${entry.id}\n${logText.slice(-2000)}`);
    }
    const bytes = readFileSync(pngPath).length;
    entries.push({
      id: entry.id,
      url: `http://127.0.0.1:5290/${entry.path}`,
      bytes,
      viewport: entry.viewport,
      renderMs: Date.now() - capturedAt,
      consoleErrors,
    });
    const errorMark = consoleErrors.length > 0 ? ` errors=${consoleErrors.length}` : "";
    process.stdout.write(`captured ${entry.id} ${bytes}b shell${errorMark}\n`);
  }
  const summary = {
    schema: CAPTURE_SUMMARY_SCHEMA,
    mode: "shell",
    origin: "http://127.0.0.1:5290",
    outDir: dest,
    startedAt,
    finishedAt: nowIso(),
    wallClockMs: Date.now() - startedMs,
    count: entries.filter((entry) => entry.skipped !== true).length,
    skippedCount: skipped.length,
    skipped,
    errorCount: entries.filter((entry) => entry.consoleErrors.length > 0).length,
    entries,
  };
  assertCaptureSummary(summary);
  writeCaptureSummary(dest, summary);
  return summary;
}

function readRun(dir) {
  const summaryPath = join(dir, "summary.json");
  if (!existsSync(summaryPath)) throw new Error(`capture summary missing: ${summaryPath}`);
  const summary = assertCaptureSummary(JSON.parse(readFileSync(summaryPath, "utf8")), summaryPath);
  return { dir: resolve(dir), summary };
}

export function diffRuns(beforeDir, afterDir, { outDir } = {}) {
  const before = readRun(beforeDir);
  const after = readRun(afterDir);
  const dest = outDir ? resolve(outDir) : join(after.dir, "diff-vs-before");
  mkdirSync(dest, { recursive: true });
  const beforeIds = new Map(before.summary.entries.filter((entry) => entry.skipped !== true).map((entry) => [entry.id, entry]));
  const afterIds = new Map(after.summary.entries.filter((entry) => entry.skipped !== true).map((entry) => [entry.id, entry]));
  const changed = [];
  const unchanged = [];
  const onlyBefore = [...beforeIds.keys()].filter((id) => !afterIds.has(id)).sort();
  const onlyAfter = [...afterIds.keys()].filter((id) => !beforeIds.has(id)).sort();
  for (const id of [...afterIds.keys()].sort()) {
    if (!beforeIds.has(id)) continue;
    const beforeFile = join(before.dir, `${id}.png`);
    const afterFile = join(after.dir, `${id}.png`);
    const delta = pixelDelta(decodePngFile(beforeFile), decodePngFile(afterFile));
    if (delta.changedPixels === 0) {
      unchanged.push(id);
      continue;
    }
    const sideBySide = join(dest, `${id}.png`);
    writeFileSync(sideBySide, sideBySidePng(decodePngFile(beforeFile), decodePngFile(afterFile)));
    changed.push({
      id,
      changedPixels: delta.changedPixels,
      totalPixels: delta.totalPixels,
      delta: delta.delta,
      dimensionMismatch: delta.dimensionMismatch,
      sideBySide,
    });
  }
  const summary = {
    schema: DIFF_SUMMARY_SCHEMA,
    method: DIFF_METHOD,
    before: before.dir,
    after: after.dir,
    outDir: dest,
    changedCount: changed.length,
    unchangedCount: unchanged.length,
    changed,
    unchanged,
    onlyBefore,
    onlyAfter,
  };
  writeFileSync(join(dest, "diff.json"), json(summary));
  return summary;
}

export function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--") {
      args._.push(...argv.slice(i + 1));
      break;
    }
    if (!token.startsWith("--")) {
      args._.push(token);
      continue;
    }
    const key = token.slice(2);
    if (key === "shell" || key === "help") {
      args[key] = true;
      continue;
    }
    const value = argv[i + 1];
    if (!value || value.startsWith("--")) throw new Error(`--${key} needs a value`);
    i += 1;
    args[key.replaceAll("-", "_")] = key === "limit" ? Number(value) : value;
  }
  return args;
}
