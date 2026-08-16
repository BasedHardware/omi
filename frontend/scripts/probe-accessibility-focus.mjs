#!/usr/bin/env node
/**
 * Rendered-layer focus probe. Not a gate: Chrome is not part of `pnpm verify`.
 * Loads production `styles.css` (or a fixture) into headless Chrome and reads
 * `getComputedStyle` after `focus({ focusVisible: true })` — the ring a
 * keyboard user sees.
 *
 * Usage:
 *   node scripts/probe-accessibility-focus.mjs
 *   node scripts/probe-accessibility-focus.mjs --without-summary
 */
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const STYLES = join(ROOT, "packages/surfaces/src/production/styles.css");
const MAGENTA = "#FF00FF";

const chromeCandidates = [
  process.env.CHROME_PATH,
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
].filter(Boolean);

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
    this.ws.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id != null && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message ?? JSON.stringify(message.error)));
        else resolve(message.result);
      }
    });
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
  const userDataDir = mkdtempSync(join(tmpdir(), "omi-a11y-focus-chrome-"));
  const chrome = spawn(chromePath(), [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--mute-audio",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--force-color-profile=srgb",
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
    const cdp = await connectCdp(`ws://127.0.0.1:${port}${path}`);
    return {
      cdp,
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

export function cssWithoutSummaryContract(css) {
  return css
    .replace(", summary, [tabindex]", ", [tabindex]")
    .replace("\n.production-shell summary:focus-visible,\n", "\n");
}

function fixtureHtml(css, focusColor, focusWidthPx) {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
:root {
  --focus: ${focusColor};
  --focus-ring-width: ${focusWidthPx}px;
  --content-primary: #111216;
  --content-secondary: #333;
  --content-tertiary: #666;
  --content-inverse: #fff;
  --surface-canvas: #ffffff;
  --surface-raised: #ffffff;
  --surface-elevated: #ececf0;
  --surface-scrim: rgba(0,0,0,0.16);
  --border: #ccc;
  --accent: #005FCC;
  --danger: #B42318;
  --success: #166A2F;
  --warning: #8A4300;
  --min-tap-target: 44px;
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 24px;
  --space-xxl: 32px;
  --space-xxxl: 40px;
  --radius-control: 12px;
  --radius-section: 16px;
  --type-body-family: sans-serif;
  --type-body-size: 16px;
  --type-body-line: 1.4;
}
${css}
</style>
</head>
<body>
  <div class="production-shell">
    <button type="button" id="probe-button">Button</button>
    <details open>
      <summary id="probe-summary">Summary</summary>
      <p>body</p>
    </details>
  </div>
</body>
</html>`;
}

const PROBE_EXPRESSION = `(() => {
  function ring(el) {
    el.focus({ focusVisible: true });
    const style = getComputedStyle(el);
    return {
      outline: style.outline,
      outlineColor: style.outlineColor,
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
      matchesFocusVisible: el.matches(":focus-visible"),
    };
  }
  return {
    button: ring(document.getElementById("probe-button")),
    summary: ring(document.getElementById("probe-summary")),
  };
})()`;

export async function probeFocusCss(css, { focusColor = MAGENTA, focusWidthPx = 2 } = {}) {
  const scratch = mkdtempSync(join(tmpdir(), "omi-a11y-focus-probe-"));
  const htmlFile = join(scratch, "probe.html");
  writeFileSync(htmlFile, fixtureHtml(css, focusColor, focusWidthPx));
  const chrome = await launchChrome();
  try {
    const created = await chrome.cdp.send("Target.createTarget", { url: "about:blank" });
    const attached = await chrome.cdp.send("Target.attachToTarget", {
      targetId: created.targetId,
      flatten: true,
    });
    const sessionId = attached.sessionId;
    const send = (method, params) => chrome.cdp.send(method, params, sessionId);
    await send("Page.enable");
    await send("Runtime.enable");
    await send("Page.navigate", { url: pathToFileURL(htmlFile).href });
    for (let attempt = 0; attempt < 50; attempt += 1) {
      const ready = await send("Runtime.evaluate", {
        expression: "document.readyState",
        returnByValue: true,
      });
      if (ready.result?.value === "complete") break;
      await delay(50);
    }
    const result = await send("Runtime.evaluate", {
      expression: PROBE_EXPRESSION,
      returnByValue: true,
      awaitPromise: false,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text ?? "probe evaluate failed");
    }
    return result.result.value;
  } finally {
    await chrome.close();
    rmSync(scratch, { recursive: true, force: true });
  }
}

const isMain = import.meta.url === pathToFileURL(resolve(process.argv[1] ?? "")).href;
if (isMain) {
  const css = readFileSync(STYLES, "utf8");
  const withoutSummary = process.argv.includes("--without-summary");
  const used = withoutSummary ? cssWithoutSummaryContract(css) : css;
  if (withoutSummary && used === css) {
    console.error("failed to strip summary from the focus contract; refusing to probe a no-op mutation");
    process.exit(2);
  }
  const measured = await probeFocusCss(used);
  console.log(JSON.stringify({
    source: withoutSummary ? "styles.css with summary removed from the focus contract" : STYLES,
    focusTokenForcedTo: MAGENTA,
    measured,
  }, null, 2));
  const summaryUsesToken = measured.summary.outlineColor === "rgb(255, 0, 255)"
    && measured.summary.outlineStyle === "solid"
    && measured.summary.outlineWidth === "2px";
  if (!withoutSummary && !summaryUsesToken) process.exit(1);
  if (withoutSummary && summaryUsesToken) process.exit(1);
}
