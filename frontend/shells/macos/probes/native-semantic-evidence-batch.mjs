#!/usr/bin/env node
/*
 * Gate-shaped coordinator for native macOS AX/keyboard evidence.
 *
 * A generic AX dump is supplementary.  Only a manifest-bound run with an
 * exact scratch PID/bundle/process, source SHAs, allowlisted landmark, and
 * (for keyboard) an observed target transition plus Escape focus restoration
 * becomes replayable native_fixture matrix coverage.
 */
import { createHash } from "node:crypto";
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const coreRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const wrapperPath = path.resolve(fileURLToPath(import.meta.url));
const nativeForbiddenForegroundPolicy = "sampled-20ms-forbidden-fixture-foreground-detection-no-activation-request";
const domains = new Set(["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"]);
const states = new Set(["ready", "error", "empty"]);
const themes = new Set(["light", "dark"]);
const widths = new Set(["compact", "regular", "wide"]);
const axAccess = new Set(["voiceover", "high_contrast", "reduced_motion", "reduced_transparency", "rtl", "text_scale_200"]);
const axRoles = new Set(["AXApplication", "AXButton", "AXCheckBox", "AXComboBox", "AXDialog", "AXGroup", "AXHeading", "AXImage", "AXLink", "AXList", "AXListItem", "AXMenu", "AXMenuItem", "AXRadioButton", "AXRow", "AXScrollArea", "AXSearchField", "AXStaticText", "AXTab", "AXTabGroup", "AXTable", "AXTextArea", "AXTextField", "AXToolbar", "AXWebArea", "AXWindow"]);
const names = new Set(["app", "main", "window", "content", "route", "home", "tasks", "memories", "conversations", "folders", "listen", "chat", "settings", "primary-navigation", "bottom-navigation", "command-palette", "command-palette-dialog", "command-input", "open-command-palette", "search", "composer", "chat-composer", "listen-transcript", "task-list", "memory-list", "conversation-list", "send", "save", "retry", "latest", "dialog", "main-window", "omi"]);
const sha40 = /^[0-9a-f]{40}$/;
const sha64 = /^[0-9a-f]{64}$/;
const runId = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const processName = /^omi-on-[A-Za-z0-9][A-Za-z0-9.-]*$/;

function fail(message, code = 2) { const error = new Error(message); error.exitCode = code; throw error; }
function sha256(value) { return createHash("sha256").update(value).digest("hex"); }
function hashFile(file) { return sha256(readFileSync(file)); }
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
function writeAtomic(file, value) {
  const temporary = `${file}.tmp-${process.pid}`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  renameSync(temporary, file);
}
function authorityRelative(file) {
  const relative = path.relative(coreRoot, file);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) fail(`path escapes core authority: ${file}`);
  return relative.split(path.sep).join("/");
}
function corePath(value, label) {
  if (!value || typeof value !== "string") fail(`${label} is required`);
  const resolved = path.isAbsolute(value) ? path.resolve(value) : path.resolve(coreRoot, value);
  if (!existsSync(resolved) || lstatSync(resolved).isSymbolicLink()) fail(`${label} must be a non-symlink path`);
  const real = realpathSync(resolved);
  const root = realpathSync(coreRoot);
  if (real !== root && !real.startsWith(`${root}${path.sep}`)) fail(`${label} must remain under core authority`);
  return real;
}
function coreFile(value, label, executable = false) {
  const file = corePath(value, label);
  if (!lstatSync(file).isFile()) fail(`${label} must be a regular file`);
  if (executable && (statSync(file).mode & 0o111) === 0) fail(`${label} must be executable`);
  return file;
}
function coreDirectory(value, label) {
  const directory = corePath(value, label);
  if (!lstatSync(directory).isDirectory()) fail(`${label} must be a directory`);
  return directory;
}
function bundleFiles(directory) {
  const files = [];
  const visit = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = path.join(current, entry.name);
      if (entry.isSymbolicLink()) fail(`fixture app must not contain symlinks: ${authorityRelative(file)}`);
      if (entry.isDirectory()) visit(file);
      else if (entry.isFile()) files.push(file);
      else fail(`fixture app contains an unsupported entry: ${authorityRelative(file)}`);
    }
  };
  visit(directory);
  return files;
}
function plistValue(plist, key) {
  const result = spawnSync("/usr/bin/plutil", ["-extract", key, "raw", "-o", "-", plist], { encoding: "utf8", timeout: 5_000 });
  if (result.status !== 0 || !result.stdout.trim()) fail(`fixture app Info.plist is missing ${key}`);
  return result.stdout.trim();
}
function fixtureApp(value, manifest) {
  const app = coreDirectory(value, "--fixture-app");
  if (!app.endsWith(".app")) fail("--fixture-app must name a .app bundle");
  const plist = coreFile(path.join(app, "Contents/Info.plist"), "fixture app Info.plist");
  const bundleId = plistValue(plist, "CFBundleIdentifier");
  const executableName = plistValue(plist, "CFBundleExecutable");
  if (!processName.test(executableName)) fail("fixture app executable must be an omi-on-* scratch process");
  const executable = coreFile(path.join(app, "Contents/MacOS", executableName), "fixture app executable", true);
  const targets = manifest.coordinates.map((coordinate) => coordinate.target);
  if (targets.some((target) => target.bundle_id !== bundleId || target.process_name !== executableName)) fail("fixture app identity does not match every selected manifest target");
  return { app, plist, bundleId, executableName, executable, files: bundleFiles(app) };
}
function outputRoot(value) {
  if (!value || typeof value !== "string") fail("--out-root is required");
  const resolved = path.isAbsolute(value) ? path.resolve(value) : path.resolve(coreRoot, value);
  if (resolved !== coreRoot && !resolved.startsWith(`${coreRoot}${path.sep}`)) fail("--out-root must remain under core authority");
  const parent = path.dirname(resolved);
  if (!existsSync(parent) || lstatSync(parent).isSymbolicLink()) fail("--out-root parent must be a real directory");
  const root = realpathSync(coreRoot);
  const realParent = realpathSync(parent);
  if (realParent !== root && !realParent.startsWith(`${root}${path.sep}`)) fail("--out-root parent must remain under core authority");
  if (existsSync(resolved) && lstatSync(resolved).isSymbolicLink()) fail("--out-root must not be a symlink");
  mkdirSync(resolved, { recursive: true });
  return resolved;
}
function inputSet(manifestPath, probePath, extra = []) {
  const files = [manifestPath, wrapperPath, probePath, ...extra];
  const entries = [...new Set(files)].map((file) => {
    const info = statSync(file);
    return { key: `core:${authorityRelative(file)}`, sha256: hashFile(file), size: info.size, mode: info.mode & 0o777 };
  }).sort((a, b) => a.key.localeCompare(b.key));
  const tree = sha256(canonical(entries));
  return { id: `input-v1-${tree}`, entries, tree_sha256: tree };
}
function parseArgs(argv) {
  const result = {};
  const flags = new Set(["prepare", "assemble_receipt", "replay_proof", "json"]);
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) fail(`unexpected argument ${token}`);
    const key = token.slice(2).replaceAll("-", "_");
    if (flags.has(key)) { result[key] = true; continue; }
    const value = argv[++index];
    if (!value || value.startsWith("--")) fail(`--${key.replaceAll("_", "-")} needs a value`);
    result[key] = value;
  }
  return result;
}
function coordinateKey(coordinate) {
  return [coordinate.kind, coordinate.domain, coordinate.shell, coordinate.state, coordinate.theme, coordinate.width, coordinate.accessibility].join("|");
}
function validateTarget(target, label) {
  if (!target || typeof target !== "object" || Object.keys(target).sort().join(",") !== "bundle_id,pid,process_name") fail(`${label}.target must bind pid,bundle_id,process_name exactly`);
  if (!Number.isInteger(target.pid) || target.pid <= 0) fail(`${label}.target.pid is invalid`);
  if (typeof target.bundle_id !== "string" || !target.bundle_id.includes("omi") || target.bundle_id.length > 128) fail(`${label}.target.bundle_id is invalid`);
  if (typeof target.process_name !== "string" || !processName.test(target.process_name)) fail(`${label}.target.process_name must be an omi-on-* scratch process`);
}
function validateCoordinate(coordinate, index, sourceShas, captureClass) {
  const required = ["accessibility", "capture_class", "domain", "expected_after", "kind", "keys", "landmark", "run_id", "schema", "shell", "source_shas", "source_tier", "state", "target", "theme", "width"];
  if (!coordinate || typeof coordinate !== "object" || Object.keys(coordinate).sort().join(",") !== required.sort().join(",")) fail(`coordinate ${index} fields are not exact`);
  if (coordinate.schema !== "omi.polish.matrix-coordinate/v1") fail(`${coordinate.run_id || index}: coordinate schema is invalid`);
  if (![`ax_snapshot`, `keyboard_trace`].includes(coordinate.kind)) fail(`${coordinate.run_id}: kind must be ax_snapshot or keyboard_trace`);
  if (!domains.has(coordinate.domain) || !states.has(coordinate.state) || !themes.has(coordinate.theme) || !widths.has(coordinate.width) || coordinate.shell !== "macos") fail(`${coordinate.run_id}: unsupported matrix coordinate`);
  if (coordinate.kind === "ax_snapshot" && !["ready", "error"].includes(coordinate.state)) fail(`${coordinate.run_id}: AX snapshot state is not applicable`);
  if (coordinate.kind === "keyboard_trace" && !["ready", "error", "empty"].includes(coordinate.state)) fail(`${coordinate.run_id}: keyboard trace state is not applicable`);
  if (coordinate.kind === "ax_snapshot" ? !axAccess.has(coordinate.accessibility) : coordinate.accessibility !== "keyboard") fail(`${coordinate.run_id}: accessibility does not match kind`);
  if (!runId.test(coordinate.run_id) || coordinate.run_id.startsWith("__")) fail(`${coordinate.run_id}: unsafe run_id`);
  if (!names.has(coordinate.landmark)) fail(`${coordinate.run_id}: landmark is not allowlisted`);
  if (!Array.isArray(coordinate.keys) || !Array.isArray(coordinate.expected_after) || coordinate.keys.length !== coordinate.expected_after.length) fail(`${coordinate.run_id}: keys/expected_after mismatch`);
  if (coordinate.kind === "ax_snapshot" && coordinate.keys.length !== 0) fail(`${coordinate.run_id}: AX snapshot cannot post keys`);
  if (coordinate.kind === "keyboard_trace" && (coordinate.keys.length === 0 || coordinate.keys.at(-1).toLowerCase() !== "escape")) fail(`${coordinate.run_id}: keyboard trace must end with Escape`);
  if (coordinate.expected_after.some((value) => value !== null && !names.has(value))) fail(`${coordinate.run_id}: expected_after contains an unallowlisted landmark`);
  if (coordinate.source_shas?.core !== sourceShas.core || coordinate.source_shas?.platform !== sourceShas.platform) fail(`${coordinate.run_id}: stale source SHAs`);
  if (coordinate.capture_class !== captureClass || coordinate.source_tier !== "native_shell") fail(`${coordinate.run_id}: capture class/tier mismatch`);
  validateTarget(coordinate.target, coordinate.run_id);
}
function loadManifest(file) {
  let manifest;
  try { manifest = JSON.parse(readFileSync(file, "utf8")); } catch (error) { fail(`manifest cannot be read: ${error.message}`); }
  const topKeys = ["capture_class", "coordinate_count", "coordinates", "schema", "source_shas", "source_tier"];
  if (manifest.schema !== "omi.polish.matrix-manifest/v1" || Object.keys(manifest).sort().join(",") !== topKeys.sort().join(",")) fail("semantic manifest schema/fields are invalid");
  if (!["native_live", "native_fixture"].includes(manifest.capture_class) || manifest.source_tier !== "native_shell") fail("semantic manifest capture class is invalid");
  if (!sha40.test(manifest.source_shas?.core || "") || !sha40.test(manifest.source_shas?.platform || "")) fail("semantic manifest source SHAs are invalid");
  if (!Array.isArray(manifest.coordinates) || manifest.coordinate_count !== manifest.coordinates.length || manifest.coordinates.length < 1 || manifest.coordinates.length > 32) fail("semantic manifest coordinate_count is invalid");
  manifest.coordinates.forEach((coordinate, index) => validateCoordinate(coordinate, index, manifest.source_shas, manifest.capture_class));
  const seen = new Set();
  for (const coordinate of manifest.coordinates) { if (seen.has(coordinate.run_id)) fail(`duplicate run_id ${coordinate.run_id}`); seen.add(coordinate.run_id); }
  return manifest;
}
function currentCoreSha(manifestSha) {
  const result = spawnSync("git", ["-C", coreRoot, "rev-parse", "HEAD"], { encoding: "utf8" });
  if (result.status === 0 && sha40.test(result.stdout.trim())) return result.stdout.trim();
  if (sha40.test(manifestSha || "")) return manifestSha;
  fail("unable to resolve current core SHA");
}
function safeEnvironment() {
  const allowed = ["PATH", "LANG", "LC_ALL", "DEVELOPER_DIR", "SDKROOT"];
  return Object.fromEntries(allowed.filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
}
function fixtureQuery(coordinate) {
  return new URLSearchParams({ polish: "1", qa: coordinate.domain, state: coordinate.state, platform: "desktop", theme: coordinate.theme, width: coordinate.width, accessibility: coordinate.accessibility, locale: "en-US" }).toString();
}
function runtimeEnvironment(coordinate, outRoot) {
  const runtime = path.join(outRoot, "runtime", coordinate.run_id);
  const home = path.join(runtime, "home"); const temporary = path.join(runtime, "tmp");
  mkdirSync(home, { recursive: true }); mkdirSync(temporary, { recursive: true });
  return {
    ...safeEnvironment(),
    HOME: home,
    TMPDIR: temporary,
    OMI_SEMANTIC_RUNTIME_DIR: runtime,
    OMI_SEMANTIC_WINDOW: "1",
    OMI_SURFACE_QUERY: fixtureQuery(coordinate),
    OMI_RUN_CLIENT_ID: coordinate.run_id,
  };
}
export function foregroundApplicationFromResults(front, info, bundleInfo) {
  const identity = front?.status === 0 && typeof front.stdout === "string" ? front.stdout.trim() : "";
  if (!/^ASN:0x[0-9a-f]+-0x[0-9a-f]+:$/i.test(identity)) fail("macOS foreground application identity is unavailable");
  if (info?.status !== 0 || typeof info.stdout !== "string") fail("macOS foreground application metadata is unavailable");
  const match = info.stdout.match(/["']?LSDisplayName["']?\s*=\s*"([^"\n]+)"/);
  if (!match?.[1]?.trim()) fail("macOS foreground application name is unavailable");
  if (bundleInfo?.status !== 0 || typeof bundleInfo.stdout !== "string") fail("macOS foreground application bundle metadata is unavailable");
  const bundleMatch = bundleInfo.stdout.match(/"CFBundleIdentifier"="([A-Za-z0-9.-]+)"/);
  if (!bundleMatch) fail("macOS foreground application bundle identity is unavailable");
  return { identity, name: match[1].trim(), bundleId: bundleMatch[1] };
}
function foregroundApplication() {
  const front = spawnSync("/usr/bin/lsappinfo", ["front"], { encoding: "utf8", timeout: 5_000 });
  const identity = front.status === 0 ? front.stdout.trim() : "";
  const info = identity ? spawnSync("/usr/bin/lsappinfo", ["info", "-only", "name", "-app", identity], { encoding: "utf8", timeout: 5_000 }) : { status: 1, stdout: "" };
  const bundleInfo = identity ? spawnSync("/usr/bin/lsappinfo", ["info", "-only", "bundleID", "-app", identity], { encoding: "utf8", timeout: 5_000 }) : { status: 1, stdout: "" };
  return foregroundApplicationFromResults(front, info, bundleInfo);
}
function assertFixtureNotForeground(bundleId, coordinate, stage) {
  const observed = foregroundApplication();
  if (observed.bundleId === bundleId) fail(`${coordinate.run_id}: semantic fixture became foreground during ${stage}`);
}
function sleepSync(milliseconds) { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds); }
function foregroundMonitorMain(bundleId, readyPath, stopPath, violationPath, donePath) {
  try {
    while (!existsSync(stopPath)) {
      try {
        const observed = foregroundApplication();
        if (observed.bundleId === bundleId) {
          writeAtomic(violationPath, { reason: "semantic fixture became foreground", observed_bundle_id: bundleId });
          return;
        }
      } catch (error) {
        writeAtomic(violationPath, { reason: error.message });
        return;
      }
      if (!existsSync(readyPath)) writeAtomic(readyPath, { forbidden_bundle_id: bundleId });
      sleepSync(20);
    }
  } finally {
    if (!existsSync(readyPath)) writeAtomic(readyPath, { forbidden_bundle_id: bundleId, failed: true });
    writeAtomic(donePath, { stopped: true });
  }
}
function startForbiddenForegroundMonitor(bundleId, outRoot, runIdValue) {
  const monitorRoot = path.join(outRoot, `.semantic-focus-monitor-${process.pid}-${runIdValue}`);
  rmSync(monitorRoot, { recursive: true, force: true });
  mkdirSync(monitorRoot, { recursive: true });
  const readyPath = path.join(monitorRoot, "ready.json"); const stopPath = path.join(monitorRoot, "stop");
  const violationPath = path.join(monitorRoot, "violation.json"); const donePath = path.join(monitorRoot, "done.json");
  const child = spawn(process.execPath, [wrapperPath, "--foreground-monitor", bundleId, readyPath, stopPath, violationPath, donePath], { cwd: coreRoot, env: safeEnvironment(), stdio: "ignore" });
  const deadline = Date.now() + 5_000;
  while (!existsSync(readyPath) && !existsSync(violationPath) && Date.now() < deadline) sleepSync(10);
  if (!existsSync(readyPath) || existsSync(violationPath)) {
    try { child.kill("SIGTERM"); } catch {}
    const detail = existsSync(violationPath) ? JSON.parse(readFileSync(violationPath, "utf8")).reason : "monitor did not become ready";
    rmSync(monitorRoot, { recursive: true, force: true });
    fail(`semantic foreground monitor unavailable: ${detail}`);
  }
  return { child, monitorRoot, stopPath, violationPath, donePath };
}
function stopForbiddenForegroundMonitor(monitor) {
  if (!monitor) return;
  writeFileSync(monitor.stopPath, "stop\n", { mode: 0o600 });
  const deadline = Date.now() + 2_000;
  while (!existsSync(monitor.donePath) && Date.now() < deadline) sleepSync(10);
  const completed = existsSync(monitor.donePath);
  let violation = null;
  if (existsSync(monitor.violationPath)) {
    try { violation = JSON.parse(readFileSync(monitor.violationPath, "utf8")); }
    catch { violation = { reason: "semantic foreground monitor wrote malformed evidence" }; }
  }
  if (!completed) { try { monitor.child.kill("SIGTERM"); } catch {} }
  rmSync(monitor.monitorRoot, { recursive: true, force: true });
  if (!completed) fail("semantic foreground monitor stopped without a terminal receipt");
  if (violation) fail(`semantic foreground custody failed: ${violation.reason}`);
}
export function lockedGuiBlock(foreground, sourceShas, coordinates) {
  if (foreground.name !== "loginwindow") return null;
  return { schema: "omi.native-semantic-blocked/v1", status: "blocked_gui_locked", reason: "native semantic evidence requires an unlocked foreground session", source_shas: sourceShas, coordinate_count: coordinates.length, run_ids: coordinates.map((coordinate) => coordinate.run_id) };
}
function childExit(child) {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve();
  return new Promise((resolve) => child.once("exit", resolve));
}
function exitWithin(exitPromise, milliseconds) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), milliseconds);
    exitPromise.then(() => { clearTimeout(timer); resolve(true); });
  });
}
async function terminateExactChild(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const exited = childExit(child);
  child.kill("SIGTERM");
  const graceful = await exitWithin(exited, 2_000);
  if (!graceful && child.exitCode === null && child.signalCode === null) {
    const killed = childExit(child);
    child.kill("SIGKILL");
    await exitWithin(killed, 2_000);
  }
}
async function launchFixture(prepared, coordinate, outRoot, readinessTimeoutMs) {
  const child = spawn(prepared.fixture.executable, [], { cwd: coreRoot, env: runtimeEnvironment(coordinate, outRoot), stdio: ["ignore", "pipe", "pipe"] });
  let stderr = "";
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => { stderr = `${stderr}${chunk}`.slice(-8_192); });
  let timer;
  const ready = new Promise((resolve, reject) => {
    const finish = (callback, value) => { clearTimeout(timer); callback(value); };
    const inspect = () => {
      if (stderr.includes("display-mode: background-semantic")) finish(resolve);
    };
    child.stderr.on("data", inspect);
    child.once("error", (error) => finish(reject, new Error(`${coordinate.run_id}: fixture launch failed: ${error.message}`)));
    child.once("exit", (code, signal) => finish(reject, new Error(`${coordinate.run_id}: fixture exited before semantic readiness (exit ${code ?? signal})`)));
    timer = setTimeout(() => finish(reject, new Error(`${coordinate.run_id}: fixture did not report background-semantic readiness within ${readinessTimeoutMs}ms`)), readinessTimeoutMs);
    inspect();
  });
  try {
    await ready;
  } catch (error) {
    await terminateExactChild(child);
    fail(`${error.message}${stderr.trim() ? `: ${stderr.trim()}` : ""}`);
  }
  if (!Number.isInteger(child.pid) || child.pid <= 0 || child.exitCode !== null) {
    await terminateExactChild(child); fail(`${coordinate.run_id}: fixture runtime PID is unavailable`);
  }
  return child;
}
function commandText(manifestPath, outRoot, preparedPath, offset, limit, replayProof, readinessTimeoutMs) {
  const args = ["node", "shells/macos/probes/native-semantic-evidence-batch.mjs", "--manifest", authorityRelative(manifestPath), "--out-root", authorityRelative(outRoot), "--offset", String(offset), "--limit", String(limit), "--prepared-input-set", authorityRelative(preparedPath), "--readiness-timeout-ms", String(readinessTimeoutMs)];
  if (replayProof) args.push("--replay-proof");
  return args.map((value) => `'${value.replaceAll("'", "'\\''")}'`).join(" ");
}
function checkProbeDocument(document, coordinate, runtimePid) {
  const expectedClass = coordinate.kind === "keyboard_trace" ? "native_keyboard_trace" : "native_ax_snapshot";
  if (!document || document.schema !== "omi.native-semantic-evidence.v2" || document.runId !== coordinate.run_id || document.coordinate !== coordinateKey(coordinate) || document.axTrusted !== true || document.evidenceClass !== expectedClass || document.matrixEligible !== true || document.domainLandmarkFound !== true) fail(`${coordinate.run_id}: probe did not produce a matrix-eligible observation`);
  if (coordinate.kind === "keyboard_trace" && document.frontmostRestored !== true) fail(`${coordinate.run_id}: probe did not restore the previously frontmost app`);
  if (document.targetPid !== runtimePid || document.target?.bound !== true || document.target.pid !== runtimePid || document.target.bundleId !== coordinate.target.bundle_id || document.target.processNameBound !== true || document.target.expectedPid !== runtimePid || document.target.expectedBundleId !== coordinate.target.bundle_id) fail(`${coordinate.run_id}: probe target binding is not exact`);
  if (document.sourceCoreSha !== coordinate.source_shas.core || document.sourcePlatformSha !== coordinate.source_shas.platform) fail(`${coordinate.run_id}: probe source binding is stale`);
  return document;
}
function evidenceDocument(coordinate, probe) {
  // Keep the evidence bytes on the verifier's exact row-document schema.  The
  // native capture class/tier stay in coverage and sidecars, never as
  // unsupported top-level evidence fields.
  const metadata = { domain: coordinate.domain, shell: coordinate.shell, state: coordinate.state, theme: coordinate.theme, width: coordinate.width, accessibility: coordinate.accessibility, run_id: coordinate.run_id, source_shas: coordinate.source_shas };
  if (coordinate.kind === "ax_snapshot") {
    const nodes = (probe.nodes || []).filter((node) => typeof node?.role === "string" && axRoles.has(node.role) && typeof node.name === "string" && names.has(node.name) && node.name.length <= 64).map((node) => ({ role: node.role, name: node.name }));
    if (!nodes.length) fail(`${coordinate.run_id}: AX evidence contains no redacted role/name nodes`);
    return { schema: "omi.polish.ax/v1", ...metadata, nodes };
  }
  const observed = probe.keys || [];
  if (observed.length !== coordinate.keys.length) fail(`${coordinate.run_id}: keyboard evidence count does not match manifest`);
  const steps = observed.map((step, index) => ({ key: step.key, action: step.targetConsumed ? (step.key.toLowerCase() === "escape" ? "restore-focus" : "target-consumed") : "posted", result: step.targetConsumed ? "observed" : "unobserved" }));
  if (!steps.length || steps.some((step, index) => step.result !== "observed" || step.key !== coordinate.keys[index] || step.key.length > 64)) fail(`${coordinate.run_id}: keyboard evidence is not target-consumed`);
  return { schema: "omi.polish.keyboard/v1", ...metadata, steps };
}
function sidecarDocument(coordinate, probe, evidence) {
  return { schema: "omi.native-semantic-sidecar/v1", coordinate: coordinateKey(coordinate), run_id: coordinate.run_id, source_shas: coordinate.source_shas, capture_class: coordinate.capture_class, source_tier: coordinate.source_tier, target: { bundle_id: coordinate.target.bundle_id, process_name: coordinate.target.process_name, process_name_bound: true, runtime_pid_redacted: true }, evidence_schema: evidence.schema, matrix_eligible: probe.matrixEligible === true, domain_landmark: coordinate.landmark, frontmost_restored: coordinate.kind === "keyboard_trace" ? probe.frontmostRestored === true : null };
}
function writePrepared(file, manifestPath, manifest, probePath, fixture, offset, limit) {
  const descriptor = { schema: "omi.native-semantic-prepared/v2", source_shas: manifest.source_shas, manifest_path: `core:${authorityRelative(manifestPath)}`, manifest_sha256: hashFile(manifestPath), shell: "macos", offset, limit, coordinate_run_ids: manifest.coordinates.slice(offset, offset + limit).map((coordinate) => coordinate.run_id), capture_class: manifest.capture_class, probe: `core:${authorityRelative(probePath)}`, fixture_app: `core:${authorityRelative(fixture.app)}`, fixture_executable: `core:${authorityRelative(fixture.executable)}`, bundle_id: fixture.bundleId, process_name: fixture.executableName, launch: { method: "direct-executable", activation_policy: "accessory", readiness: "stderr:display-mode: background-semantic" }, authority: { fixture: true, bridge: "disabled", credentials: false, production_api: false, focus_policy: { ax: nativeForbiddenForegroundPolicy, keyboard: "explicit-temporary-focus-consent-and-proven-restoration" } }, input_set: inputSet(manifestPath, probePath, fixture.files) };
  writeAtomic(file, descriptor);
  return descriptor;
}
function captureRange(args, manifest) {
  const offset = Number(args.offset || 0); const limit = Number(args.limit || manifest.coordinates.length - offset);
  if (!Number.isInteger(offset) || !Number.isInteger(limit) || offset < 0 || limit < 1 || offset + limit > manifest.coordinates.length) fail("semantic capture range is invalid");
  return { offset, limit };
}
function loadPrepared(file, manifestPath, manifest, offset, limit) {
  const descriptor = JSON.parse(readFileSync(file, "utf8"));
  const descriptorKeys = ["authority", "bundle_id", "capture_class", "coordinate_run_ids", "fixture_app", "fixture_executable", "input_set", "launch", "limit", "manifest_path", "manifest_sha256", "offset", "probe", "process_name", "schema", "shell", "source_shas"];
  if (descriptor.schema !== "omi.native-semantic-prepared/v2" || Object.keys(descriptor).sort().join(",") !== descriptorKeys.sort().join(",") || descriptor.source_shas.core !== manifest.source_shas.core || descriptor.source_shas.platform !== manifest.source_shas.platform || descriptor.manifest_path !== `core:${authorityRelative(manifestPath)}` || descriptor.manifest_sha256 !== hashFile(manifestPath) || descriptor.capture_class !== manifest.capture_class || descriptor.shell !== "macos" || descriptor.offset !== offset || descriptor.limit !== limit) fail("prepared semantic input set is stale");
  if (manifest.capture_class !== "native_fixture" || canonical(descriptor.authority) !== canonical({ fixture: true, bridge: "disabled", credentials: false, production_api: false, focus_policy: { ax: nativeForbiddenForegroundPolicy, keyboard: "explicit-temporary-focus-consent-and-proven-restoration" } })) fail("prepared semantic authority is not fixture-only");
  if (canonical(descriptor.launch) !== canonical({ method: "direct-executable", activation_policy: "accessory", readiness: "stderr:display-mode: background-semantic" })) fail("prepared semantic launch policy is invalid");
  const expectedRunIds = manifest.coordinates.slice(offset, offset + limit).map((coordinate) => coordinate.run_id);
  if (canonical(descriptor.coordinate_run_ids) !== canonical(expectedRunIds)) fail("prepared semantic coordinate range is stale");
  const probePath = coreFile(String(descriptor.probe || "").replace(/^core:/, ""), "prepared probe", true);
  const fixture = fixtureApp(String(descriptor.fixture_app || "").replace(/^core:/, ""), manifest);
  if (descriptor.fixture_executable !== `core:${authorityRelative(fixture.executable)}` || descriptor.bundle_id !== fixture.bundleId || descriptor.process_name !== fixture.executableName) fail("prepared semantic fixture identity is stale");
  if (canonical(descriptor.input_set) !== canonical(inputSet(manifestPath, probePath, fixture.files))) fail("prepared semantic input set file list/hash is stale");
  // The descriptor is an immutable prepared input. It is excluded from
  // descriptor.input_set to avoid a self-hash cycle, then included in the
  // capture command's effective input set below.
  return { descriptor, probePath, fixture, input: inputSet(manifestPath, probePath, [...fixture.files, file]) };
}
function canonicalBatchId(inputSetId, command, members) { return `batch-v1-${sha256(canonical({ command, input_set_id: inputSetId, members }))}`; }
async function capture(args, manifestPath, manifest, outRoot, preparedPath) {
  const { offset, limit } = captureRange(args, manifest);
  const prepared = loadPrepared(preparedPath, manifestPath, manifest, offset, limit);
  const readinessTimeoutMs = Number(args.readiness_timeout_ms || 15_000);
  if (!Number.isInteger(readinessTimeoutMs) || readinessTimeoutMs < 100 || readinessTimeoutMs > 30_000) fail("--readiness-timeout-ms must be 100..30000");
  const selectedCoordinates = manifest.coordinates.slice(offset, offset + limit);
  if (selectedCoordinates.some((coordinate) => coordinate.kind === "keyboard_trace") && process.env.OMI_ALLOW_TEMPORARY_FOCUS !== "1") {
    const blocked = {
      schema: "omi.native-semantic-blocked/v1",
      status: "blocked_user_focus",
      reason: "keyboard_trace requires explicit OMI_ALLOW_TEMPORARY_FOCUS=1 operator consent",
      source_shas: manifest.source_shas,
      coordinate_count: limit,
      run_ids: selectedCoordinates.map((coordinate) => coordinate.run_id),
    };
    process.stdout.write(`${JSON.stringify(blocked)}\n`);
    process.exitCode = 3;
    return;
  }
  const preflightForeground = foregroundApplication();
  const guiBlock = lockedGuiBlock(preflightForeground, manifest.source_shas, selectedCoordinates);
  if (guiBlock) {
    process.stdout.write(`${JSON.stringify(guiBlock)}\n`);
    process.exitCode = 3;
    return;
  }
  const command = commandText(manifestPath, outRoot, preparedPath, offset, limit, Boolean(args.replay_proof), readinessTimeoutMs);
  const records = {}; const captureRoot = path.join(outRoot, "captures", "macos"); mkdirSync(captureRoot, { recursive: true });
  const stdoutLine = `NATIVE_SEMANTIC_BATCH_COMPLETE members=${limit}\n`;
  const observe = async (coordinate) => {
    const foregroundMonitor = coordinate.kind === "ax_snapshot"
      ? startForbiddenForegroundMonitor(prepared.fixture.bundleId, outRoot, coordinate.run_id)
      : null;
    let child = null;
    try {
      child = await launchFixture(prepared, coordinate, outRoot, readinessTimeoutMs);
      assertFixtureNotForeground(prepared.fixture.bundleId, coordinate, "fixture launch");
      const probeArgs = ["--pid", String(child.pid), "--bundle-id", coordinate.target.bundle_id, "--expected-bundle-id", coordinate.target.bundle_id, "--expected-process-name", coordinate.target.process_name, "--run-id", coordinate.run_id, "--source-core-sha", coordinate.source_shas.core, "--source-platform-sha", coordinate.source_shas.platform, "--coordinate", coordinateKey(coordinate), "--kind", coordinate.kind, "--landmark", coordinate.landmark, "--require-matrix", "--json"];
      if (coordinate.kind === "keyboard_trace") probeArgs.push("--expect-after", coordinate.expected_after.map((value) => value || "-").join(","), "--activate", "--keys", coordinate.keys.join(","));
      const result = spawnSync(prepared.probePath, probeArgs, { cwd: coreRoot, env: safeEnvironment(), encoding: "utf8", timeout: 120_000 });
      let probe; try { probe = JSON.parse(result.stdout || "{}"); } catch { fail(`${coordinate.run_id}: probe did not emit JSON`); }
      if (result.status !== 0) fail(`${coordinate.run_id}: probe failed: ${(result.stderr || probe.error || "probe failure").trim()}`);
      if (child.exitCode !== null || child.signalCode !== null) fail(`${coordinate.run_id}: fixture exited during semantic probe`);
      checkProbeDocument(probe, coordinate, child.pid);
      const evidence = evidenceDocument(coordinate, probe);
      return { evidence, sidecar: sidecarDocument(coordinate, probe, evidence) };
    } finally {
      try {
        if (child) await terminateExactChild(child);
        assertFixtureNotForeground(prepared.fixture.bundleId, coordinate, "semantic cleanup");
      } finally {
        stopForbiddenForegroundMonitor(foregroundMonitor);
      }
    }
  };
  for (const [index, coordinate] of selectedCoordinates.entries()) {
    rmSync(path.join(outRoot, "runtime", coordinate.run_id), { recursive: true, force: true });
    const primary = await observe(coordinate);
    if (args.replay_proof) {
      const replay = await observe(coordinate);
      if (canonical(primary.evidence) !== canonical(replay.evidence) || canonical(primary.sidecar) !== canonical(replay.sidecar)) fail(`${coordinate.run_id}: replay proof bytes differ`);
    }
    const evidencePath = path.join(captureRoot, `${coordinate.run_id}.json`); const sidecarPath = `${evidencePath}.sidecar.json`; writeAtomic(evidencePath, primary.evidence); writeAtomic(sidecarPath, primary.sidecar);
    records[`m${String(index).padStart(4, "0")}`] = { coordinate: [coordinate.kind, coordinate.domain, coordinate.shell, coordinate.state, coordinate.theme, coordinate.width, coordinate.accessibility], run_id: coordinate.run_id, evidence: { root: "core", path: authorityRelative(evidencePath), sha256: hashFile(evidencePath) }, sidecar: { root: "core", path: authorityRelative(sidecarPath), sha256: hashFile(sidecarPath) } };
  }
  const resultPath = path.join(outRoot, "batch-result.json");
  writeAtomic(resultPath, { schema: "omi.polish.native-semantic-batch-result/v1", source_shas: manifest.source_shas, manifest_path: `core:${authorityRelative(manifestPath)}`, manifest_sha256: hashFile(manifestPath), command, argv: ["node", "shells/macos/probes/native-semantic-evidence-batch.mjs", "--manifest", authorityRelative(manifestPath), "--out-root", authorityRelative(outRoot), "--offset", String(offset), "--limit", String(limit), "--prepared-input-set", authorityRelative(preparedPath), "--readiness-timeout-ms", String(readinessTimeoutMs), ...(args.replay_proof ? ["--replay-proof"] : [])], input_set: prepared.input, members: records, coordinate_count: Object.keys(records).length, stdout_sha256: sha256(stdoutLine), stderr_sha256: sha256(""), authority: prepared.descriptor.authority, replay_proof: Boolean(args.replay_proof) });
  process.stdout.write(stdoutLine);
}
function assemble(args, manifestPath, manifest, outRoot) {
  const resultPath = coreFile(args.result_path, "--result-path"); const result = JSON.parse(readFileSync(resultPath, "utf8"));
  if (result.schema !== "omi.polish.native-semantic-batch-result/v1" || result.manifest_path !== `core:${authorityRelative(manifestPath)}` || result.manifest_sha256 !== hashFile(manifestPath) || canonical(result.source_shas) !== canonical(manifest.source_shas) || !result.input_set?.id || typeof result.command !== "string" || !Array.isArray(result.argv) || !result.members || typeof result.members !== "object") fail("batch result is stale or malformed");
  if (!Array.isArray(result.input_set.entries) || !sha64.test(result.input_set.tree_sha256 || "") || result.input_set.id !== `input-v1-${result.input_set.tree_sha256}` || sha256(canonical(result.input_set.entries)) !== result.input_set.tree_sha256 || result.coordinate_count !== Object.keys(result.members).length) fail("batch result input set or member count is malformed");
  if (result.replay_proof !== true || !result.argv.includes("--replay-proof")) fail("batch result lacks a completed replay proof");
  const members = result.members; const batchId = canonicalBatchId(result.input_set.id, result.command, members); const artifactHashes = {}; const before = {}; const created = {}; const seenRuns = new Set();
  for (const [memberId, member] of Object.entries(members)) {
    if (!/^m\d{4}$/.test(memberId) || !Array.isArray(member.coordinate) || member.coordinate.length !== 7 || typeof member.run_id !== "string" || member.evidence?.root !== "core" || member.sidecar?.root !== "core") fail("batch result member is malformed");
    if (seenRuns.has(member.run_id)) fail("batch result contains duplicate run_id"); seenRuns.add(member.run_id);
    const coordinate = manifest.coordinates.find((entry) => entry.run_id === member.run_id);
    if (!coordinate || canonical(member.coordinate) !== canonical([coordinate.kind, coordinate.domain, coordinate.shell, coordinate.state, coordinate.theme, coordinate.width, coordinate.accessibility])) fail("batch result member is not bound to the manifest");
    for (const [artifact, label] of [[member.evidence, "evidence"], [member.sidecar, "sidecar"]]) {
      if (typeof artifact.path !== "string" || !sha64.test(artifact.sha256 || "")) fail(`batch result ${label} artifact is malformed`);
      const file = coreFile(artifact.path, `batch result ${label}`); if (hashFile(file) !== artifact.sha256) fail(`batch result ${label} hash is stale`);
    }
  }
  const bind = (artifact, isCreated = true) => { const key = `${artifact.root}:${artifact.path}`; artifactHashes[key] = artifact.sha256; before[key] = null; created[key] = isCreated; };
  bind({ root: "core", path: authorityRelative(resultPath), sha256: hashFile(resultPath) }); for (const member of Object.values(members)) { bind(member.evidence); bind(member.sidecar); }
  const now = new Date().toISOString(); const receipt = { argv: result.argv, cwd: ".", cwd_root: "core", exit_code: 0, timeout_seconds: 300, started_at: args.started_at || now, finished_at: args.finished_at || now, run_id: batchId, source_shas: result.source_shas, stdout_sha256: result.stdout_sha256, stderr_sha256: result.stderr_sha256, artifact_hashes: artifactHashes, artifact_before_hashes: before, artifact_created: created, capture_class: manifest.capture_class, source_tier: "native_shell", input_set: result.input_set, batch_id: batchId, batch_members: members };
  const coverage = Object.values(members).map((member, index) => { const [kind, domain, shell, state, theme, width, accessibility] = member.coordinate; return { kind, domain, shell, state, theme, width, accessibility, capture_class: manifest.capture_class, source_tier: "native_shell", root: member.evidence.root, path: member.evidence.path, sha256: member.evidence.sha256, command: result.command, command_ran: true, command_receipt: receipt, run_id: member.run_id, sidecar: member.sidecar.path, source_shas: result.source_shas, input_set_id: result.input_set.id, batch_id: batchId, batch_member: `m${String(index).padStart(4, "0")}` }; });
  const output = { schema: "omi.polish.native-semantic-batch/v1", batch_id: batchId, command: result.command, command_receipt: receipt, input_set: result.input_set, batch_members: members, coverage, manifest_path: result.manifest_path, manifest_sha256: result.manifest_sha256, source_shas: result.source_shas, coordinate_count: coverage.length, authority: result.authority };
  const receiptPath = path.join(outRoot, `${batchId}.receipt.json`); writeAtomic(receiptPath, output); process.stdout.write(`NATIVE_SEMANTIC_RECEIPT: ${batchId} file=${authorityRelative(receiptPath)}\n`);
}
async function main() {
  const args = parseArgs(process.argv.slice(2)); if (!args.manifest || !args.out_root) fail("--manifest and --out-root are required"); const manifestPath = coreFile(args.manifest, "--manifest"); const manifest = loadManifest(manifestPath); if (currentCoreSha(manifest.source_shas.core) !== manifest.source_shas.core) fail("manifest core SHA does not match current core HEAD"); const outRoot = outputRoot(args.out_root);
  if (args.assemble_receipt) return assemble(args, manifestPath, manifest, outRoot);
  if (manifest.capture_class !== "native_fixture") fail("replayable macOS semantic capture requires native_fixture authority");
  if (args.prepare) { const { offset, limit } = captureRange(args, manifest); const probePath = coreFile(args.probe, "--probe", true); const fixture = fixtureApp(args.fixture_app, manifest); const descriptorPath = path.join(outRoot, "prepared-input-set.json"); const descriptor = writePrepared(descriptorPath, manifestPath, manifest, probePath, fixture, offset, limit); process.stdout.write(`NATIVE_SEMANTIC_PREPARED: ${descriptor.input_set.id} file=${authorityRelative(descriptorPath)}\n`); return; }
  if (!args.prepared_input_set) fail("capture requires --prepared-input-set");
  return await capture(args, manifestPath, manifest, outRoot, coreFile(args.prepared_input_set, "--prepared-input-set"));
}
if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  if (process.argv[2] === "--foreground-monitor") foregroundMonitorMain(...process.argv.slice(3, 8));
  else try { await main(); } catch (error) { console.error(`ERROR: ${error.message}`); process.exitCode = error.exitCode || 2; }
}
