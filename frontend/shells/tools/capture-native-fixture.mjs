#!/usr/bin/env node
/**
 * Produce one native_fixture screenshot coordinate.
 *
 * This command deliberately owns only offline fixture captures.  It never
 * receives a backend URL/token and refuses browser-preview capture classes.
 * The shell launchers perform the native rendering; this wrapper binds the
 * exact query, source SHA, run id and image hash into a verifier sidecar and
 * receipt.
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const toolRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const domains = new Set(["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"]);
const states = new Set(["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"]);
const themes = new Set(["light", "dark"]);
const widths = new Set(["compact", "regular", "wide"]);
const accessibility = new Set(["none", "keyboard", "voiceover", "high_contrast", "reduced_motion", "reduced_transparency", "rtl", "text_scale_200"]);
const shells = new Set(["macos", "ios"]);
const safeId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const sha = /^[0-9a-f]{40}$/;

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exitCode = 2;
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!arg.startsWith("--")) throw new Error(`unexpected argument '${arg}'`);
    const key = arg.slice(2);
    if (key === "help") return { help: true };
    const value = argv[++i];
    if (!value || value.startsWith("--")) throw new Error(`--${key} needs a value`);
    out[key.replaceAll("-", "_")] = value;
  }
  return out;
}

function absoluteOutput(value, label) {
  if (!value || !path.isAbsolute(value)) throw new Error(`${label} must be an absolute path`);
  const resolved = path.resolve(value);
  if (!resolved.startsWith(`${toolRoot}${path.sep}`)) {
    throw new Error(`${label} must be inside the core worktree`);
  }
  return resolved;
}

function json(value) {
  return JSON.stringify(value, null, 2) + "\n";
}

function hashFile(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}

function isoNow() {
  return new Date().toISOString();
}

function currentCoreSha() {
  const result = spawnSync("git", ["-C", toolRoot, "rev-parse", "HEAD"], { encoding: "utf8" });
  if (result.status !== 0) throw new Error("unable to resolve core HEAD");
  const value = result.stdout.trim();
  if (!sha.test(value)) throw new Error("core HEAD is not a full SHA");
  return value;
}

function validateManifest(manifest) {
  if (!manifest || manifest.schema !== "omi.polish.matrix-coordinate/v1") throw new Error("manifest schema must be omi.polish.matrix-coordinate/v1");
  if (manifest.kind !== "screenshot") throw new Error("manifest kind must be screenshot");
  if (!domains.has(manifest.domain)) throw new Error(`unknown domain '${manifest.domain}'`);
  if (!shells.has(manifest.shell)) throw new Error(`unknown shell '${manifest.shell}'`);
  if (!states.has(manifest.state)) throw new Error(`unknown state '${manifest.state}'`);
  if (!themes.has(manifest.theme)) throw new Error(`unknown theme '${manifest.theme}'`);
  if (!widths.has(manifest.width)) throw new Error(`unknown width '${manifest.width}'`);
  if (!accessibility.has(manifest.accessibility)) throw new Error(`unknown accessibility mode '${manifest.accessibility}'`);
  if (!safeId.test(manifest.run_id) || manifest.run_id === "anonymous" || manifest.run_id === "overflow") throw new Error("run_id is unsafe");
  if (manifest.capture_class !== "native_fixture") throw new Error("capture_class must be native_fixture");
  if (manifest.source_tier !== "native_shell") throw new Error("source_tier must be native_shell");
  if (!manifest.source_shas || typeof manifest.source_shas !== "object" || !sha.test(manifest.source_shas.core) || !sha.test(manifest.source_shas.platform)) throw new Error("source_shas.core/platform must be full SHAs");
  if (!manifest.viewport || !Number.isInteger(manifest.viewport.width) || !Number.isInteger(manifest.viewport.height) || !Number.isFinite(manifest.viewport.scale) || manifest.viewport.width < 320 || manifest.viewport.width > 2400 || manifest.viewport.height < 320 || manifest.viewport.height > 2600 || manifest.viewport.scale <= 0 || manifest.viewport.scale > 4) throw new Error("viewport must contain bounded width, height and scale");
  if (!Number.isInteger(manifest.viewport.width) || !Number.isInteger(manifest.viewport.height)) throw new Error("viewport dimensions must be integers");
}

function main() {
  let args;
  try { args = parseArgs(process.argv.slice(2)); } catch (error) { fail(error.message); return; }
  if (args.help) {
    console.log("usage: capture-native-fixture.mjs --manifest coordinate.json [--output path] [--sidecar path] [--receipt path]");
    return;
  }
  if (!args.manifest) { fail("--manifest is required"); return; }
  const manifestPath = path.resolve(args.manifest);
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
    validateManifest(manifest);
  } catch (error) { fail(`invalid manifest: ${error.message}`); return; }
  let coreSha;
  try { coreSha = currentCoreSha(); } catch (error) { fail(error.message); return; }
  if (manifest.source_shas.core !== coreSha) { fail(`manifest core SHA ${manifest.source_shas.core} does not match current core HEAD ${coreSha}`); return; }

  const output = args.output ? absoluteOutput(args.output, "--output") : path.join(toolRoot, ".build", "polish-native-fixture", `${manifest.run_id}.png`);
  const sidecar = args.sidecar ? absoluteOutput(args.sidecar, "--sidecar") : `${output}.sidecar.json`;
  const receipt = args.receipt ? absoluteOutput(args.receipt, "--receipt") : `${output}.receipt.json`;
  mkdirSync(path.dirname(output), { recursive: true });
  rmSync(output, { force: true });
  rmSync(sidecar, { force: true });
  rmSync(receipt, { force: true });

  const query = new URLSearchParams({ qa: manifest.domain, polish: "1", state: manifest.state, theme: manifest.theme, platform: manifest.shell === "macos" ? "desktop" : "mobile", accessibility: manifest.accessibility }).toString();
  const launcher = manifest.shell === "macos" ? path.join(toolRoot, "shells/macos/scripts/dev-capture-macos.sh") : path.join(toolRoot, "shells/ios/scripts/dev-run-ios.sh");
  const launcherArgs = ["--fixture", manifest.domain, "--state", manifest.state, "--theme", manifest.theme, "--accessibility", manifest.accessibility, "--run-id", manifest.run_id, "--capture-out", output];
  if (manifest.shell === "macos") launcherArgs.push("--viewport-width", String(manifest.viewport.width), "--viewport-height", String(manifest.viewport.height));
  const started = isoNow();
  // Do not hand the native launcher the agent's ambient environment.  In
  // particular, credentials and host Flutter caches are outside this proof's
  // authority.  A scratch HOME/PUB_CACHE keeps build writes recoverable and
  // prevents a fixture run from mutating a user's toolchain.
  const allowedEnvironmentKeys = ["PATH", "TMPDIR", "LANG", "LC_ALL", "DEVELOPER_DIR", "SDKROOT", "OMI_SURFACES_DIST", "FLUTTER_BIN", "NODE_BIN"];
  const env = Object.fromEntries(allowedEnvironmentKeys.filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
  const scratchHome = path.join(toolRoot, ".build", "polish-native-fixture", "home");
  mkdirSync(scratchHome, { recursive: true });
  env.HOME = scratchHome;
  env.PUB_CACHE = path.join(scratchHome, ".pub-cache");
  env.XDG_CACHE_HOME = path.join(scratchHome, ".cache");
  env.OMI_APP_NAME = `omi-on-polish-fixture-${manifest.run_id}`;
  env.OMI_SURFACE_PORT = "5290";
  env.OMI_FIXTURE_CAPTURE_WAIT_SECONDS = "5";
  const timeoutSeconds = 300;
  const result = spawnSync("/bin/bash", [launcher, ...launcherArgs], { cwd: toolRoot, env, stdio: "inherit", encoding: "utf8", timeout: timeoutSeconds * 1000 });
  const finished = isoNow();
  if (result.status !== 0 || !existsSync(output)) { rmSync(output, { force: true }); fail(`native ${manifest.shell} launcher failed (exit ${result.status ?? "signal"})`); return; }
  const image = readFileSync(output);
  const pngMagic = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  if (image.length < 100 || !image.subarray(0, 8).equals(pngMagic)) { rmSync(output, { force: true }); fail("capture output is not a nonempty PNG"); return; }
  const imageSha = hashFile(output);
  const relativeImage = path.relative(toolRoot, output);
  const bound = { schema: "omi.polish.screenshot/v1", domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme, width: manifest.width, accessibility: manifest.accessibility, run_id: manifest.run_id, source_shas: manifest.source_shas, capture_class: manifest.capture_class, source_tier: manifest.source_tier, image_root: "core", image_path: relativeImage, image_sha256: imageSha };
  writeFileSync(sidecar, json(bound), { mode: 0o600 });
  writeFileSync(receipt, json({ schema: "omi.polish.native-fixture/v1", run_id: manifest.run_id, capture_class: manifest.capture_class, source_tier: manifest.source_tier, source_shas: manifest.source_shas, surface_query: query, viewport: manifest.viewport, capture: { fixture: true, shell: manifest.shell, method: manifest.shell === "macos" ? "WKWebView.takeSnapshot" : "xcrun simctl io screenshot" }, image_root: "core", image_path: relativeImage, image_sha256: imageSha, command: { argv: [launcher, ...launcherArgs], exit_code: result.status, started_at: started, finished_at: finished, timeout_seconds: timeoutSeconds } }), { mode: 0o600 });
  console.log(`NATIVE_FIXTURE_CAPTURE: ${relativeImage} sha256=${imageSha} run_id=${manifest.run_id}`);
}

try { main(); } catch (error) { fail(error.message); }
