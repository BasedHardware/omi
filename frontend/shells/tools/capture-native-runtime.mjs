#!/usr/bin/env node
/**
 * Produce one native shell runtime coordinate from a real WebView.
 *
 * This is deliberately separate from screenshot and semantic capture.  The
 * macOS path runs the fixture WKWebView and reads a typed OMI_PROBE_JS result;
 * the iOS path runs the fixture UI test and reads the typed host marker exposed
 * by OmiUiWebView only when OMI_POLISH_RUNTIME_PROBE=1.  No browser preview or
 * hand-authored lifecycle/style value is accepted.
 */
import { createHash } from "node:crypto";
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const coreRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const macRoot = path.join(coreRoot, "shells/macos");
const iosRoot = path.join(coreRoot, "shells/ios");
const foregroundGuard = path.join(coreRoot, "shells/tools/macos-foreground-guard.mjs");
const forbiddenForegroundBundleIds = [
  "com.apple.iphonesimulator",
  "me.omi.proto.omiWebviewProto",
  "me.omi.shell.core-tasks.prototype",
];
const safeId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const sha = /^[0-9a-f]{40}$/;
const domains = new Set(["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"]);
const states = new Set(["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"]);
const themes = new Set(["light", "dark"]);
const shells = new Set(["macos", "ios"]);
const accessibilities = new Set(["none", "reduced_motion", "reduced_transparency"]);
const runtimeApplicability = {
  memories: new Set(["ready", "offline", "busy"]),
  tasks: new Set(["ready", "offline", "busy", "complete"]),
  conversations: new Set(["ready", "offline", "busy"]),
  folders: new Set(["ready", "offline"]),
  chat: new Set(["ready", "offline", "busy", "complete", "cancelled"]),
  listen: new Set(["ready", "offline", "busy", "complete"]),
  settings: new Set(["ready", "offline"]),
};
const styles = {
  reduced_motion: {
    computed_style: {
      transition_duration: new Set(["0s", "0ms", "0", "none"]),
      transition_property: new Set(["none"]),
      animation_name: new Set(["none"]),
      animation_duration: new Set(["0s", "0ms", "0", "none"]),
      motion_policy: new Set(["disabled", "reduced", "none"]),
    },
    native_runtime: { motion_policy: new Set(["disabled", "reduced", "none"]) },
  },
  reduced_transparency: {
    computed_style: {
      backdrop_filter: new Set(["none"]),
      material_transparency: new Set(["solid", "opaque", "disabled", "none"]),
      transparency_policy: new Set(["solid", "opaque", "disabled", "none"]),
    },
    native_runtime: { transparency_policy: new Set(["solid", "opaque", "disabled", "none"]) },
  },
};
const eventTypes = new Set(["lifecycle", "computed_style", "native_runtime"]);
const namePattern = /^[a-z][a-z0-9_.-]{0,63}$/;
const valuePattern = /^[A-Za-z0-9][A-Za-z0-9 ._():,/%+-]{0,255}$/;
const secretPattern = /(?:api[_-]?key|authorization|bearer|password|secret|access[_-]?token|cookie|private[_-]?key)/i;

function sha256(bytes) { return createHash("sha256").update(bytes).digest("hex"); }
export function runtimeFixtureName(domain) { return domain === "memories" ? "memories-platform" : domain; }
function stable(value) { return `${JSON.stringify(value)}\n`; }
function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]));
  return value;
}
function canonicalBytes(value) { return Buffer.from(JSON.stringify(canonicalValue(value))); }
function fail(message) { console.error(`ERROR: ${message}`); process.exitCode = 2; }
function readJson(file, label) {
  try { return JSON.parse(readFileSync(file, "utf8")); }
  catch (error) { throw new Error(`${label} is not valid JSON: ${error instanceof Error ? error.message : String(error)}`); }
}
function parseArgs(argv) {
  const out = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help") return { help: true };
    if (!arg.startsWith("--")) throw new Error(`unexpected argument '${arg}'`);
    const key = arg.slice(2).replaceAll("-", "_");
    const value = argv[++index];
    if (!value || value.startsWith("--")) throw new Error(`--${key} needs a value`);
    out[key] = value;
  }
  return out;
}
function insideCore(file, label) {
  if (!path.isAbsolute(file)) throw new Error(`${label} must be absolute`);
  const resolved = path.resolve(file);
  if (!resolved.startsWith(`${coreRoot}${path.sep}`)) throw new Error(`${label} must be inside the core worktree`);
  return resolved;
}
function gitHead(root) {
  const result = spawnSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" });
  if (result.status !== 0) throw new Error(`unable to resolve ${root} HEAD`);
  const value = result.stdout.trim();
  if (!sha.test(value)) throw new Error(`${root} HEAD is not a full SHA`);
  return value;
}

export function validateManifest(manifest) {
  const expected = ["accessibility", "capture_class", "device", "domain", "kind", "run_id", "schema", "shell", "source_shas", "source_tier", "state", "surface_query", "theme", "viewport", "width"];
  if (!manifest || Object.keys(manifest).sort().join(",") !== expected.sort().join(",")) throw new Error("manifest has unexpected or missing keys");
  if (manifest.schema !== "omi.polish.matrix-coordinate/v1" || manifest.kind !== "runtime_trace") throw new Error("manifest must be a runtime_trace matrix coordinate");
  if (!domains.has(manifest.domain) || !shells.has(manifest.shell) || !states.has(manifest.state) || !themes.has(manifest.theme) || !accessibilities.has(manifest.accessibility)) throw new Error("manifest has an unsupported coordinate value");
  if (!runtimeApplicability[manifest.domain]?.has(manifest.state)) throw new Error(`runtime state is not applicable to ${manifest.domain}`);
  if (manifest.accessibility !== "none" && manifest.state !== "ready") throw new Error("reduced accessibility runtime coordinates require state=ready");
  if (manifest.width !== "regular") throw new Error("runtime coordinates require width=regular");
  if (!safeId.test(manifest.run_id) || manifest.run_id === "anonymous" || manifest.run_id === "overflow") throw new Error("run_id is unsafe");
  if (manifest.capture_class !== "native_fixture" || manifest.source_tier !== "native_shell") throw new Error("runtime matrix capture must be native_fixture/native_shell");
  if (!manifest.source_shas || Object.keys(manifest.source_shas).sort().join(",") !== "core,platform" || !sha.test(manifest.source_shas.core) || !sha.test(manifest.source_shas.platform)) throw new Error("source_shas.core/platform must be full SHAs");
  if (!manifest.viewport || Object.keys(manifest.viewport).sort().join(",") !== "height,scale,width" || !Number.isInteger(manifest.viewport.width) || !Number.isInteger(manifest.viewport.height) || !Number.isFinite(manifest.viewport.scale) || manifest.viewport.width < 320 || manifest.viewport.width > 2400 || manifest.viewport.height < 320 || manifest.viewport.height > 2800 || manifest.viewport.scale <= 0 || manifest.viewport.scale > 4) throw new Error("viewport must contain bounded width, height and scale");
  if (!manifest.device || Object.keys(manifest.device).sort().join(",") !== "model,orientation,udid" || typeof manifest.device.model !== "string" || !/^[A-Za-z0-9][A-Za-z0-9 .(),_-]{0,95}$/.test(manifest.device.model) || !["portrait", "landscape"].includes(manifest.device.orientation) || typeof manifest.device.udid !== "string" || !/^(?:[A-F0-9-]{36}|macos-local)$/.test(manifest.device.udid)) throw new Error("device must contain exact model/orientation/udid binding");
  if (typeof manifest.surface_query !== "string" || manifest.surface_query.length < 1 || manifest.surface_query.length > 512) throw new Error("surface_query must be a bounded string");
  const query = new URLSearchParams(manifest.surface_query);
  const queryKeys = [...query.keys()].sort();
  const expectedQa = runtimeFixtureName(manifest.domain);
  if (queryKeys.join(",") !== "accessibility,locale,platform,polish,qa,state,theme,width" || query.get("polish") !== "1" || query.get("qa") !== expectedQa || query.get("state") !== manifest.state || query.get("theme") !== manifest.theme || query.get("width") !== manifest.width || query.get("accessibility") !== manifest.accessibility || query.get("locale") !== "en-US" || query.get("platform") !== (manifest.shell === "ios" ? "mobile" : "desktop")) throw new Error("surface_query does not match the runtime coordinate");
  return manifest;
}

function metadata(manifest) {
  return {
    domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme,
    width: manifest.width, accessibility: manifest.accessibility, run_id: manifest.run_id,
    source_shas: manifest.source_shas, capture_class: manifest.capture_class, source_tier: manifest.source_tier,
  };
}

function validateForegroundCustody(custody) {
  if (!custody || custody.schema !== "omi.macos-foreground-guard/v1" || custody.status !== 0 || custody.error !== null || custody.monitor_error !== null) throw new Error("runtime preparation lacks successful foreground custody");
  if (custody.policy !== "sampled-macos-forbidden-fixture-foreground-detection-20ms-target-250ms-probe-timeout-no-activation-request" || JSON.stringify(custody.forbidden_bundle_ids) !== JSON.stringify([...forbiddenForegroundBundleIds].sort()) || custody.target_interval_milliseconds !== 20 || custody.probe_timeout_milliseconds !== 250 || !Number.isInteger(custody.sample_count) || custody.sample_count < 1 || !Number.isFinite(custody.max_sample_gap_milliseconds) || custody.max_sample_gap_milliseconds < 0) throw new Error("runtime preparation foreground custody policy is malformed");
}

function validateGuardedPreparation(preparation, manifest, inputPath, inputBytes) {
  const command = preparation?.command;
  if (!command || !Array.isArray(command.argv) || command.argv.length < 12 || command.exit_code !== 0 || command.signal !== undefined && command.signal !== null || command.cwd_root !== "core" || !["", "."].includes(command.cwd) || command.timeout_seconds !== 310 || !/^[0-9a-f]{64}$/.test(command.stdout_sha256 || "") || !/^[0-9a-f]{64}$/.test(command.stderr_sha256 || "")) throw new Error("runtime preparation command is not a successful guarded launcher");
  const guardIndex = command.argv.findIndex((value) => typeof value === "string" && value.endsWith("/shells/tools/macos-foreground-guard.mjs"));
  const separator = command.argv.indexOf("--");
  const forbidIndex = command.argv.indexOf("--forbid-bundle-ids");
  if (guardIndex !== 1 || separator < 0 || forbidIndex < 0 || command.argv[forbidIndex + 1] !== forbiddenForegroundBundleIds.join(",") || !command.argv.includes("--result") || !command.argv.includes("--stdout") || !command.argv.includes("--stderr") || !command.argv.includes("--timeout") || command.argv[command.argv.indexOf("--timeout") + 1] !== "300") throw new Error("runtime preparation command is not the exact foreground-guard invocation");
  const guardedCommand = command.argv[separator + 1];
  const guardedArgs = command.argv.slice(separator + 2);
  if (manifest.shell === "macos") {
    if (guardedCommand !== "/bin/bash" || !guardedArgs[0]?.endsWith("/shells/macos/scripts/dev-run-macos.sh") || !guardedArgs.includes("--fixture") || !guardedArgs.includes(runtimeFixtureName(manifest.domain)) || !guardedArgs.includes("--run-id") || !guardedArgs.includes(manifest.run_id)) throw new Error("macOS runtime preparation did not guard the exact fixture launcher");
  } else if (guardedCommand !== "xcodebuild" || !guardedArgs.includes("-only-testing:RunnerUITests/NativeRuntimeEvidenceUITests/testNativeRuntimeEvidence")) {
    throw new Error("iOS runtime preparation did not guard the exact native runtime test");
  }
  const expectedPath = path.relative(coreRoot, inputPath);
  if (preparation.artifact?.root !== "core" || preparation.artifact?.path !== expectedPath || preparation.artifact?.sha256 !== sha256(inputBytes)) throw new Error("runtime preparation artifact authority does not match replay input");
}

export function validateEvent(event) {
  if (!event || typeof event !== "object" || Object.keys(event).sort().join(",") !== "name,passed,type,value") throw new Error("runtime event keys are not exact");
  if (!eventTypes.has(event.type) || typeof event.name !== "string" || !namePattern.test(event.name) || typeof event.value !== "string" || !valuePattern.test(event.value) || event.passed !== true) throw new Error("runtime event is malformed or unpassed");
  if (event.type === "lifecycle" && (event.name !== "state" || !states.has(event.value))) throw new Error("lifecycle event must be state=<known state>");
  if (event.type !== "lifecycle") {
    const allowed = Object.values(styles).flatMap((mode) => Object.entries(mode)).flatMap(([type, names]) => Object.entries(names).map(([name, values]) => [`${type}:${name}`, values]));
    const values = new Map(allowed).get(`${event.type}:${event.name}`);
    if (!values || !values.has(event.value)) throw new Error("runtime style/native event value is not allowlisted");
  }
  return event;
}

export function validateHostMarker(marker, manifest) {
  const expected = ["accessibility", "domain", "events", "schema", "theme"].sort().join(",");
  if (!marker || typeof marker !== "object" || Object.keys(marker).sort().join(",") !== expected) throw new Error("native runtime marker keys are not exact");
  if (marker.schema !== "omi.native-runtime-marker/v1" || marker.domain !== manifest.domain || marker.theme !== manifest.theme || marker.accessibility !== manifest.accessibility) throw new Error("native runtime marker metadata does not match manifest");
  if (!Array.isArray(marker.events) || marker.events.length === 0 || marker.events.length > 16) throw new Error("native runtime marker events must be nonempty and bounded");
  if (marker.events.some((event) => secretPattern.test(JSON.stringify(event)))) throw new Error("native runtime marker contains secret-like text");
  marker.events.forEach(validateEvent);
  if (manifest.accessibility === "none" && !marker.events.some((event) => event.type === "lifecycle" && event.name === "state" && event.value === manifest.state)) throw new Error("native runtime marker did not observe the covered lifecycle state");
  if (manifest.accessibility !== "none") {
    const allow = styles[manifest.accessibility];
    if (!marker.events.some((event) => allow[event.type]?.[event.name]?.has(event.value))) throw new Error(`native runtime marker did not observe ${manifest.accessibility}`);
  }
  return marker;
}

export function validateRuntimeArtifact(document, manifest) {
  const expected = ["accessibility", "capture_class", "domain", "events", "run_id", "schema", "shell", "source_shas", "source_tier", "state", "theme", "width"].sort().join(",");
  if (!document || typeof document !== "object" || Object.keys(document).sort().join(",") !== expected) throw new Error("runtime artifact keys are not exact");
  if (document.schema !== "omi.polish.runtime/v1") throw new Error("runtime artifact schema mismatch");
  const expectedMetadata = metadata(manifest);
  for (const [key, value] of Object.entries(expectedMetadata)) if (JSON.stringify(document[key]) !== JSON.stringify(value)) throw new Error(`runtime artifact ${key} does not match manifest`);
  if (!Array.isArray(document.events) || document.events.length === 0) throw new Error("runtime artifact events must be nonempty");
  document.events.forEach(validateEvent);
  if (manifest.accessibility === "none" && !document.events.some((event) => event.type === "lifecycle" && event.name === "state" && event.value === manifest.state)) throw new Error("runtime artifact did not observe the covered lifecycle state");
  if (manifest.accessibility !== "none" && !document.events.some((event) => styles[manifest.accessibility][event.type]?.[event.name]?.has(event.value))) throw new Error(`runtime artifact did not observe ${manifest.accessibility}`);
  return document;
}

export function runtimeProbeScript(manifest) {
  // Return one JSON string, rather than a JS object, because the AppKit shell's
  // diagnostic line is intentionally text-only.  Only allowlisted DOM state or
  // computed style values are retained; labels, values, and credentials never
  // cross the shell boundary.
  const domain = JSON.stringify(manifest.domain);
  const qa = JSON.stringify(runtimeFixtureName(manifest.domain));
  const access = JSON.stringify(manifest.accessibility);
  const state = JSON.stringify(manifest.state);
  const theme = JSON.stringify(manifest.theme);
  return `(() => { const q = new URL(location.href).searchParams; const expectedDomain = ${domain}; const expectedQa = ${qa}; const expectedAccess = ${access}; const expectedState = ${state}; const expectedTheme = ${theme}; const requestedQa = q.get('qa') || ''; const access = q.get('accessibility') || ''; const wanted = q.get('state') || ''; const theme = q.get('theme') || ''; const renderedTheme = document.documentElement.dataset.themeSelection || ''; const polishState = document.documentElement.dataset.polishState || ''; const root = document.querySelector('main[data-production-shell]'); if (requestedQa !== expectedQa || access !== expectedAccess || wanted !== expectedState || theme !== expectedTheme || renderedTheme !== expectedTheme || polishState !== expectedState || !root || root.dataset.route !== expectedDomain) return 'OMI_RUNTIME_PENDING'; const target = root.querySelector('*') || root; const style = getComputedStyle(target); const events = []; if (access === 'none') events.push({type:'lifecycle',name:'state',value:polishState,passed:true}); else if (access === 'reduced_motion') { events.push({type:'computed_style',name:'transition_duration',value:style.transitionDuration || '',passed:true}); events.push({type:'computed_style',name:'animation_name',value:style.animationName || '',passed:true}); events.push({type:'computed_style',name:'animation_duration',value:style.animationDuration || '',passed:true}); } else if (access === 'reduced_transparency') events.push({type:'computed_style',name:'backdrop_filter',value:style.backdropFilter || '',passed:true}); return JSON.stringify({schema:'omi.native-runtime-marker/v1',domain:expectedDomain,theme,accessibility:access,events}); })()`;
}

function allowedEnvironment() {
  const keys = ["PATH", "TMPDIR", "LANG", "LC_ALL", "DEVELOPER_DIR", "SDKROOT", "OMI_SURFACES_DIST", "FLUTTER_BIN", "NODE_BIN"];
  return Object.fromEntries(keys.filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
}

export function parseMacProbe(output, manifest) {
  const matches = [...output.matchAll(/^PROBE_JS:\s*(\{.*\})\s+error:\s*none\s*$/gm)];
  if (matches.length !== 1) throw new Error(`macOS WK probe must emit exactly one successful marker (found ${matches.length})`);
  let marker;
  try { marker = JSON.parse(matches[0][1]); } catch (error) { throw new Error(`macOS WK probe marker is not JSON: ${error.message}`); }
  return validateHostMarker(marker, manifest);
}

export function macRuntimeAppName(runId) {
  if (!safeId.test(runId)) throw new Error("runtime run_id is malformed");
  return `omi-on-runtime-${sha256(Buffer.from(runId)).slice(0, 16)}`;
}

function runMac(manifest, outputDir) {
  const launcher = path.join(macRoot, "scripts/dev-run-macos.sh");
  const screenshot = path.join(outputDir, "probe.png");
  mkdirSync(outputDir, { recursive: true });
  const env = allowedEnvironment();
  const surfacesDist = path.resolve(env.OMI_SURFACES_DIST || path.join(coreRoot, "packages/surfaces/dist"));
  if (!surfacesDist.startsWith(`${coreRoot}${path.sep}`) || !existsSync(path.join(surfacesDist, "index.html"))) throw new Error("OMI_SURFACES_DIST must be an existing core-owned surfaces dist");
  env.OMI_SURFACES_DIST = surfacesDist;
  const scratch = path.join(outputDir, "home");
  mkdirSync(scratch, { recursive: true });
  env.HOME = scratch; env.PUB_CACHE = path.join(scratch, ".pub-cache"); env.XDG_CACHE_HOME = path.join(scratch, ".cache");
  // The launcher deliberately accepts only short scratch bundle names. Matrix
  // run IDs contain underscores and coordinate prose, so bind them through a
  // deterministic digest instead of weakening that native-shell boundary.
  env.OMI_APP_NAME = macRuntimeAppName(manifest.run_id);
  env.OMI_SURFACE_PORT = "5290"; env.OMI_FIXTURE_CAPTURE_WAIT_SECONDS = "5";
  env.OMI_PROBE_JS = runtimeProbeScript(manifest); env.OMI_PROBE_DELAY = "5"; env.OMI_PROBE_SETTLE = "1";
  env.OMI_PROBE_PENDING_VALUE = "OMI_RUNTIME_PENDING";
  env.OMI_PROBE_MAX_ATTEMPTS = "50";
  env.OMI_PROBE_RETRY_INTERVAL = "0.1";
  env.OMI_ACCEPTANCE_WAIT_SECONDS = "30";
  const args = ["--fixture", runtimeFixtureName(manifest.domain), "--state", manifest.state, "--theme", manifest.theme, "--accessibility", manifest.accessibility, "--run-id", manifest.run_id, "--capture-out", screenshot, "--viewport-width", String(manifest.viewport.width), "--viewport-height", String(manifest.viewport.height)];
  const guardResult = path.join(outputDir, "foreground-guard.json");
  const stdoutPath = path.join(outputDir, "foreground-guard.stdout.log");
  const stderrPath = path.join(outputDir, "foreground-guard.stderr.log");
  const guardArgs = [
    foregroundGuard,
    "--result", guardResult,
    "--stdout", stdoutPath,
    "--stderr", stderrPath,
    "--timeout", "300",
    "--forbid-bundle-ids", forbiddenForegroundBundleIds.join(","),
    "--", "/bin/bash", launcher, ...args,
  ];
  const started = new Date();
  const guarded = spawnSync(process.execPath, guardArgs, { cwd: coreRoot, env, encoding: "utf8", timeout: 310_000, maxBuffer: 64 * 1024 * 1024 });
  const finished = new Date();
  if (!existsSync(guardResult)) throw new Error("macOS runtime foreground guard produced no terminal receipt");
  const custody = readJson(guardResult, "macOS runtime foreground guard");
  validateForegroundCustody(custody);
  if (guarded.status !== 0) throw new Error(`macOS native runtime foreground custody failed (${custody.monitor_error || custody.error || custody.status || guarded.status})`);
  const stdout = readFileSync(stdoutPath, "utf8");
  const stderr = readFileSync(stderrPath, "utf8");
  const log = path.join(coreRoot, ".build/polish-fixture", `${env.OMI_APP_NAME}.run.log`);
  const combined = `${stdout}\n${stderr}\n${existsSync(log) ? readFileSync(log, "utf8") : ""}`;
  const marker = parseMacProbe(combined, manifest);
  // The PNG exists only to drive the fixture launcher's bounded exit path; it
  // is deliberately not retained or presented as runtime evidence.
  rmSync(screenshot, { force: true });
  return {
    marker,
    started,
    finished,
    argv: [process.execPath, ...guardArgs],
    stdout,
    stderr,
    probe: runtimeProbeScript(manifest),
    foregroundCustody: custody,
    commandTimeoutSeconds: 310,
  };
}

function inputEntry(file, relative) {
  const info = lstatSync(file);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`replay input must be a regular file: ${relative}`);
  const bytes = readFileSync(file);
  return { key: `core:${relative}`, sha256: sha256(bytes), size: bytes.length, mode: info.mode & 0o777 };
}
function inputTree(entries) {
  return sha256(canonicalBytes(entries.slice().sort((a, b) => a.key.localeCompare(b.key))));
}
function makeInputSet(entries) {
  const sorted = entries.slice().sort((a, b) => a.key.localeCompare(b.key));
  const tree = inputTree(sorted);
  return { id: `input-v1-${tree}`, entries: sorted, tree_sha256: tree };
}
function relativeCore(file, label) {
  const resolved = insideCore(file, label); const relative = path.relative(coreRoot, resolved);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error(`${label} must be inside core`);
  return { resolved, relative };
}

export function gateReplay(manifest, manifestPath, inputPath, outputPath, outputDir, emitRecords = true) {
  validateManifest(manifest);
  const input = relativeCore(inputPath, "--replay-input"); const output = relativeCore(outputPath, "--replay-output"); const manifestFile = relativeCore(manifestPath, "--manifest");
  if (input.resolved === output.resolved) throw new Error("replay input and output must differ");
  const inputBytes = readFileSync(input.resolved); const artifact = JSON.parse(inputBytes.toString("utf8")); validateRuntimeArtifact(artifact, manifest);
  const preparationPath = path.join(path.dirname(input.resolved), "runtime-preparation-receipt.json");
  if (!existsSync(preparationPath)) throw new Error("runtime replay requires its preparation receipt");
  const preparation = readJson(preparationPath, "runtime preparation receipt");
  if (preparation.schema !== "omi.polish.runtime-preparation/v1" || preparation.run_id !== manifest.run_id || JSON.stringify(preparation.source_shas) !== JSON.stringify(manifest.source_shas) || preparation.capture_class !== manifest.capture_class || preparation.source_tier !== manifest.source_tier) throw new Error("runtime preparation receipt does not match replay artifact");
  validateGuardedPreparation(preparation, manifest, input.resolved, inputBytes);
  validateForegroundCustody(preparation.foreground_custody);
  const artifactBytes = Buffer.from(stable(artifact));
  if (sha256(artifactBytes) !== sha256(inputBytes)) throw new Error("replay input must use canonical JSON formatting");
  mkdirSync(path.dirname(output.resolved), { recursive: true });
  writeFileSync(output.resolved, artifactBytes, { mode: 0o600, flag: "wx" });
  const producerFile = relativeCore(path.resolve(fileURLToPath(import.meta.url)), "producer script");
  const preparationFile = relativeCore(preparationPath, "preparation receipt");
  const entries = [inputEntry(manifestFile.resolved, manifestFile.relative), inputEntry(producerFile.resolved, producerFile.relative), inputEntry(input.resolved, input.relative), inputEntry(preparationFile.resolved, preparationFile.relative)];
  const guardFile = relativeCore(foregroundGuard, "foreground guard");
  entries.push(inputEntry(guardFile.resolved, guardFile.relative));
  const inputSet = makeInputSet(entries);
  const outputHash = sha256(artifactBytes);
  const command = `node ${path.relative(coreRoot, producerFile.resolved)} --manifest ${manifestFile.relative} --replay-input ${input.relative} --replay-output ${output.relative} --emit-gate-records false`;
  const member = { coordinate: ["runtime_trace", manifest.domain, manifest.shell, manifest.state, manifest.theme, manifest.width, manifest.accessibility], run_id: manifest.run_id, evidence: { root: "core", path: output.relative, sha256: outputHash }, sidecar: null };
  const batchMembers = { m0: member };
  const batchId = `batch-v1-${sha256(canonicalBytes({ command, input_set_id: inputSet.id, members: batchMembers }))}`;
  const now = new Date().toISOString();
  const replayOutput = `NATIVE_RUNTIME_REPLAY: kind=runtime_trace path=${output.relative}`;
  const receipt = {
    argv: ["node", path.relative(coreRoot, producerFile.resolved), "--manifest", manifestFile.relative, "--replay-input", input.relative, "--replay-output", output.relative, "--emit-gate-records", "false"],
    cwd: ".", cwd_root: "core", exit_code: 0, timeout_seconds: 30, started_at: now, finished_at: now,
    run_id: batchId, source_shas: manifest.source_shas, stdout_sha256: sha256(Buffer.from(`${replayOutput}\n`)), stderr_sha256: sha256(Buffer.from("")),
    artifact_hashes: { [`core:${output.relative}`]: outputHash }, artifact_before_hashes: { [`core:${output.relative}`]: null }, artifact_created: { [`core:${output.relative}`]: true },
    capture_class: manifest.capture_class, source_tier: manifest.source_tier, input_set: inputSet, batch_id: batchId, batch_members: batchMembers,
  };
  mkdirSync(outputDir, { recursive: true });
  const receiptPath = path.join(outputDir, "native-runtime-command-receipt.json"); const coveragePath = path.join(outputDir, "native-runtime-coverage.json");
  if (emitRecords) {
    writeFileSync(receiptPath, stable(receipt), { mode: 0o600 });
    writeFileSync(coveragePath, stable({ coverage: [{ kind: "runtime_trace", domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme, width: manifest.width, accessibility: manifest.accessibility, capture_class: manifest.capture_class, source_tier: manifest.source_tier, root: "core", path: output.relative, sha256: outputHash, command, command_ran: true, command_receipt: receipt, run_id: manifest.run_id, sidecar: null, source_shas: manifest.source_shas, input_set_id: inputSet.id, batch_id: batchId, batch_member: "m0" }] }), { mode: 0o600 });
  }
  console.log(replayOutput);
  return { receiptPath, coveragePath, receipt };
}

function runIos(manifest, outputDir) {
  const device = manifest.device.udid;
  const project = path.join(iosRoot, "app/ios/Runner.xcodeproj");
  const testOnly = "RunnerUITests/NativeRuntimeEvidenceUITests/testNativeRuntimeEvidence";
  const resultBundle = path.join(outputDir, "Runner.xcresult");
  const env = allowedEnvironment();
  const scratch = path.join(outputDir, "home"); mkdirSync(scratch, { recursive: true }); env.HOME = scratch; env.PUB_CACHE = path.join(scratch, ".pub-cache"); env.XDG_CACHE_HOME = path.join(scratch, ".cache");
  mkdirSync(outputDir, { recursive: true });
  const surfacesDist = process.env.SURFACES_DIST || process.env.OMI_SURFACES_DIST;
  const resolvedSurfacesDist = surfacesDist ? path.resolve(surfacesDist) : "";
  if (!resolvedSurfacesDist.startsWith(`${coreRoot}${path.sep}`) || !existsSync(path.join(resolvedSurfacesDist, "index.html"))) throw new Error("SURFACES_DIST must point to an existing core-owned surfaces dist/index.html");
  env.SURFACES_DIST = resolvedSurfacesDist;
  const nodeBin = env.NODE_BIN || process.execPath;
  const flutterBin = env.FLUTTER_BIN || path.join(process.env.HOME || "/Users/dazheng", ".local/share/mise/installs/flutter/3.44.5/bin/flutter");
  const inventory = spawnSync("xcrun", ["simctl", "list", "devices", "-j"], { cwd: coreRoot, env, encoding: "utf8", timeout: 30_000 });
  if (inventory.status !== 0) throw new Error("iOS simulator inventory is unavailable");
  let inventoryDocument;
  try { inventoryDocument = JSON.parse(inventory.stdout); } catch { throw new Error("iOS simulator inventory is malformed"); }
  const boundDevice = Object.values(inventoryDocument.devices || {}).flat().find((candidate) => candidate.udid === device);
  if (!boundDevice || boundDevice.state !== "Booted" || boundDevice.name !== manifest.device.model) throw new Error("manifest iOS simulator is not the exact booted device");
  const query = manifest.surface_query;
  const bundle = spawnSync(nodeBin, [path.join(iosRoot, "tools/build-surfaces-bundle.mjs")], { cwd: coreRoot, env, encoding: "utf8", timeout: 120_000, maxBuffer: 16 * 1024 * 1024 });
  if (bundle.status !== 0) throw new Error(`iOS surfaces bundle preparation failed (${bundle.status ?? "signal"})`);
  const flutterArgs = ["build", "ios", "--simulator", "--debug", "--dart-define=SURFACE_MODE=scheme", "--dart-define=SCHEME_BUNDLE=surfaces", `--dart-define=SURFACE_QUERY=${query}`];
  const flutter = spawnSync(flutterBin, flutterArgs, { cwd: path.join(iosRoot, "app"), env, encoding: "utf8", timeout: 300_000, maxBuffer: 64 * 1024 * 1024 });
  if (flutter.status !== 0) throw new Error(`iOS Flutter fixture build failed (${flutter.status ?? "signal"})`);
  const args = ["test", "-project", project, "-scheme", "Runner", "-destination", `platform=iOS Simulator,id=${device}`, "-only-testing", testOnly, "-parallel-testing-enabled", "NO", "-derivedDataPath", path.join(outputDir, "DerivedData"), "-resultBundlePath", resultBundle, "CODE_SIGNING_ALLOWED=NO", `FLUTTER_ROOT=${path.dirname(path.dirname(flutterBin))}`];
  const started = new Date();
  const guardResult = path.join(outputDir, "foreground-guard.json");
  const stdoutPath = path.join(outputDir, "xcodebuild.stdout");
  const stderrPath = path.join(outputDir, "xcodebuild.stderr");
  const guarded = spawnSync(process.execPath, [foregroundGuard, "--result", guardResult, "--stdout", stdoutPath, "--stderr", stderrPath, "--timeout", "300", "--forbid-bundle-ids", forbiddenForegroundBundleIds.join(","), "--", "xcodebuild", ...args], { cwd: path.join(iosRoot, "app"), env, encoding: "utf8", timeout: 310_000, maxBuffer: 16 * 1024 * 1024 });
  const finished = new Date();
  if (!existsSync(guardResult)) throw new Error("iOS runtime foreground guard produced no terminal receipt");
  const custody = readJson(guardResult, "iOS runtime foreground guard");
  if (guarded.status !== 0 || custody.schema !== "omi.macos-foreground-guard/v1" || custody.monitor_error !== null || custody.error !== null || custody.status !== 0) throw new Error(`iOS native runtime foreground custody failed (${custody.monitor_error || custody.error || custody.status || guarded.status})`);
  const result = { status: custody.status, stdout: readFileSync(stdoutPath, "utf8"), stderr: readFileSync(stderrPath, "utf8") };
  const exportDir = path.join(outputDir, "attachments"); mkdirSync(exportDir, { recursive: true });
  const testIdentifier = "test://com.apple.xcode/Runner/RunnerUITests/NativeRuntimeEvidenceUITests/testNativeRuntimeEvidence";
  const exported = spawnSync("xcrun", ["xcresulttool", "export", "attachments", "--path", resultBundle, "--output-path", exportDir, "--test-id", testIdentifier], { cwd: coreRoot, env, encoding: "utf8", timeout: 30_000, maxBuffer: 16 * 1024 * 1024 });
  if (exported.status !== 0) throw new Error(`iOS runtime attachment export failed (${exported.status ?? "signal"})`);
  const exportedManifest = readJson(path.join(exportDir, "manifest.json"), "iOS runtime attachment manifest");
  if (!Array.isArray(exportedManifest) || exportedManifest.length !== 1 || !Array.isArray(exportedManifest[0].attachments)) throw new Error("iOS runtime attachment manifest is not exact");
  const attachments = exportedManifest[0].attachments.filter((item) => typeof item.suggestedHumanReadableName === "string" && /^OMI_NATIVE_IOS_RUNTIME_JSON(?:_\d+_[0-9A-F-]{36})?\.json$/.test(item.suggestedHumanReadableName));
  if (attachments.length !== 1 || typeof attachments[0].exportedFileName !== "string" || !/^[A-Za-z0-9-]+\.json$/.test(attachments[0].exportedFileName)) throw new Error("iOS runtime UI test must retain exactly one typed host marker");
  const markerFile = path.join(exportDir, attachments[0].exportedFileName);
  if (!existsSync(markerFile) || !statSync(markerFile).isFile()) throw new Error("iOS runtime host marker bytes are missing");
  const marker = validateHostMarker(readJson(markerFile, "iOS runtime marker"), manifest);
  return { marker, started, finished, argv: [process.execPath, foregroundGuard, "--result", guardResult, "--stdout", stdoutPath, "--stderr", stderrPath, "--timeout", "300", "--forbid-bundle-ids", forbiddenForegroundBundleIds.join(","), "--", "xcodebuild", ...args], stdout: result.stdout || "", stderr: result.stderr || "", commandTimeoutSeconds: 310, query, foregroundCustody: custody, buildCommands: { surfaces: [nodeBin, path.join(iosRoot, "tools/build-surfaces-bundle.mjs")], surfaces_stdout_sha256: sha256(Buffer.from(bundle.stdout || "")), surfaces_stderr_sha256: sha256(Buffer.from(bundle.stderr || "")), flutter: [flutterBin, ...flutterArgs], flutter_stdout_sha256: sha256(Buffer.from(flutter.stdout || "")), flutter_stderr_sha256: sha256(Buffer.from(flutter.stderr || "")) } };
}

function main() {
  let args;
  try { args = parseArgs(process.argv.slice(2)); } catch (error) { fail(error.message); return; }
  if (args.help) { console.log("usage: capture-native-runtime.mjs --manifest coordinate.json [--output-dir /abs/core/.build/..] [--replay-input artifact.json --replay-output output.json]"); return; }
  if (!args.manifest) { fail("--manifest is required"); return; }
  const manifestPath = path.resolve(args.manifest); let manifest;
  try { manifest = validateManifest(readJson(manifestPath, "manifest")); } catch (error) { fail(`invalid manifest: ${error.message}`); return; }
  let coreSha;
  try { coreSha = gitHead(coreRoot); } catch (error) { fail(error.message); return; }
  if (manifest.source_shas.core !== coreSha) { fail(`manifest core SHA ${manifest.source_shas.core} does not match current core HEAD ${coreSha}`); return; }
  const platformRoot = args.platform_root || process.env.OMI_PLATFORM_ROOT;
  // Prepared replay is source-custodied by the immutable input set and does
  // not need a host checkout.  Live capture must independently resolve the
  // platform worktree before touching a shell.
  if (!args.replay_input && !platformRoot) { fail("--platform-root or OMI_PLATFORM_ROOT is required to prove platform SHA"); return; }
  if (!args.replay_input && platformRoot) {
    try { if (gitHead(path.resolve(platformRoot)) !== manifest.source_shas.platform) throw new Error(`manifest platform SHA ${manifest.source_shas.platform} does not match current platform HEAD`); } catch (error) { fail(error.message); return; }
  }
  const outputDir = args.output_dir ? insideCore(args.output_dir, "--output-dir") : path.join(coreRoot, ".build/polish-native-runtime", manifest.run_id);
  mkdirSync(outputDir, { recursive: true });
  if (args.replay_input || args.replay_output) {
    if (!args.replay_input || !args.replay_output) { fail("--replay-input and --replay-output must be provided together"); return; }
    try { gateReplay(manifest, manifestPath, path.resolve(args.replay_input), path.resolve(args.replay_output), outputDir, args.emit_gate_records !== "false"); } catch (error) { fail(error.message); }
    return;
  }
  let capture;
  try { capture = manifest.shell === "macos" ? runMac(manifest, outputDir) : runIos(manifest, outputDir); } catch (error) { fail(error instanceof Error ? error.message : String(error)); return; }
  const artifact = { schema: "omi.polish.runtime/v1", ...metadata(manifest), events: capture.marker.events };
  const artifactPath = path.join(outputDir, "runtime.json"); const artifactBytes = Buffer.from(stable(artifact)); writeFileSync(artifactPath, artifactBytes, { mode: 0o600 });
  const receipt = { schema: "omi.polish.runtime-preparation/v1", ...metadata(manifest), command: { argv: capture.argv, cwd: path.relative(coreRoot, coreRoot), cwd_root: "core", exit_code: 0, started_at: capture.started.toISOString(), finished_at: capture.finished.toISOString(), timeout_seconds: capture.commandTimeoutSeconds || 300, stdout_sha256: sha256(Buffer.from(capture.stdout)), stderr_sha256: sha256(Buffer.from(capture.stderr)) }, ...(capture.query ? { surface_query: capture.query, build_commands: capture.buildCommands } : {}), ...(capture.foregroundCustody ? { foreground_custody: capture.foregroundCustody } : {}), artifact: { root: "core", path: path.relative(coreRoot, artifactPath), sha256: sha256(artifactBytes) } };
  writeFileSync(path.join(outputDir, "runtime-preparation-receipt.json"), stable(receipt), { mode: 0o600 });
  console.log(`NATIVE_RUNTIME_EVIDENCE: path=${path.relative(coreRoot, artifactPath)} sha256=${sha256(artifactBytes)} run_id=${manifest.run_id}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  try { main(); } catch (error) { fail(error instanceof Error ? error.message : String(error)); }
}
