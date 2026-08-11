#!/usr/bin/env node
/**
 * Run the fixture-only iOS UI-test target and turn its one JSON attachment into
 * verifier-owned AX and keyboard artifacts.  The test target never receives
 * credentials or arbitrary user text; this wrapper binds the exact coordinate,
 * source SHAs, capture class, run id and xcodebuild receipt around the native
 * result bundle.
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const iosRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const coreRoot = path.resolve(iosRoot, "../..");
const project = path.join(iosRoot, "app/ios/Runner.xcodeproj");
const scheme = "Runner";
const testIdentifier = "test://com.apple.xcode/Runner/RunnerUITests/NativeSemanticEvidenceUITests/testChatReadySemanticEvidence";
const testOnly = "RunnerUITests/NativeSemanticEvidenceUITests/testChatReadySemanticEvidence";
const domains = new Set(["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"]);
const states = new Set(["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"]);
const themes = new Set(["light", "dark"]);
const widths = new Set(["compact", "regular", "wide"]);
const accessibilities = new Set(["none", "keyboard", "voiceover", "high_contrast", "reduced_motion", "reduced_transparency", "rtl", "text_scale_200"]);
const safeId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const sha = /^[0-9a-f]{40}$/;
const allowedRoles = new Set(["application", "web-view", "button", "text-field", "static-text"]);
const allowedNames = new Set(["Omi", "Omi surface", "Memories", "Tasks", "Conversations", "Folders", "Listen", "Chat", "Settings", "Search", "Send", "Close", "Cancel", "Try again", "All Conversations"]);
const allowedActions = new Set(["launch", "tap", "typeText", "typeKey"]);
const allowedResults = new Set(["foreground", "accepted", "web-view-accepted", "keyboard-visible", "keyboard-not-observed", "sent"]);

function stableJson(value) {
  return `${JSON.stringify(value)}\n`;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help") return { help: true };
    if (!arg.startsWith("--")) throw new Error(`unexpected argument '${arg}'`);
    const key = arg.slice(2).replaceAll("-", "_");
    const value = argv[++i];
    if (!value || value.startsWith("--")) throw new Error(`--${key} needs a value`);
    out[key] = value;
  }
  return out;
}

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exitCode = 2;
}

function readJson(file, label) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch (error) {
    throw new Error(`${label} is not valid JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function insideCore(file, label) {
  if (!path.isAbsolute(file)) throw new Error(`${label} must be an absolute path`);
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

function validateManifest(manifest) {
  const expectedKeys = ["accessibility", "capture_class", "domain", "kind", "run_id", "schema", "shell", "source_shas", "source_tier", "state", "theme", "viewport", "width"];
  if (!manifest || Object.keys(manifest).sort().join(",") !== expectedKeys.join(",")) throw new Error("manifest has unexpected or missing keys");
  if (!manifest || manifest.schema !== "omi.polish.matrix-coordinate/v1") throw new Error("manifest schema must be omi.polish.matrix-coordinate/v1");
  if (manifest.kind !== "semantic") throw new Error("manifest kind must be semantic");
  if (!domains.has(manifest.domain)) throw new Error(`unknown domain '${manifest.domain}'`);
  if (manifest.shell !== "ios") throw new Error("native semantic producer only supports shell=ios");
  if (!states.has(manifest.state)) throw new Error(`unknown state '${manifest.state}'`);
  if (!themes.has(manifest.theme)) throw new Error(`unknown theme '${manifest.theme}'`);
  if (!widths.has(manifest.width)) throw new Error(`unknown width '${manifest.width}'`);
  if (!accessibilities.has(manifest.accessibility)) throw new Error(`unknown accessibility '${manifest.accessibility}'`);
  if (!safeId.test(manifest.run_id) || manifest.run_id === "anonymous" || manifest.run_id === "overflow") throw new Error("run_id is unsafe");
  if (manifest.capture_class !== "native_fixture") throw new Error("capture_class must be native_fixture");
  if (manifest.source_tier !== "native_shell") throw new Error("source_tier must be native_shell");
  if (!manifest.source_shas || typeof manifest.source_shas !== "object" || Object.keys(manifest.source_shas).sort().join(",") !== "core,platform" || !sha.test(manifest.source_shas.core) || !sha.test(manifest.source_shas.platform)) throw new Error("source_shas.core/platform must be full SHAs");
  if (!manifest.viewport || typeof manifest.viewport !== "object" || Object.keys(manifest.viewport).sort().join(",") !== "height,scale,width" || !Number.isInteger(manifest.viewport.width) || !Number.isInteger(manifest.viewport.height) || !Number.isFinite(manifest.viewport.scale) || manifest.viewport.width < 320 || manifest.viewport.width > 2400 || manifest.viewport.height < 320 || manifest.viewport.height > 2800 || manifest.viewport.scale <= 0 || manifest.viewport.scale > 4) throw new Error("viewport must contain bounded width, height and scale");
  if (manifest.accessibility !== "none") throw new Error("iOS semantic fixture currently proves accessibility=none only");
}

function validateMarker(marker) {
  if (!marker || typeof marker !== "object") throw new Error("native attachment must be an object");
  const keys = Object.keys(marker).sort();
  if (keys.join(",") !== "bundleId,nodes,schema,steps") throw new Error("native attachment has unexpected top-level keys");
  if (marker.schema !== "omi.native-ios-semantic-marker.v1") throw new Error("native attachment schema mismatch");
  if (marker.bundleId !== "me.omi.proto.omiWebviewProto") throw new Error("native attachment bundle id mismatch");
  if (!Array.isArray(marker.nodes) || marker.nodes.length === 0) throw new Error("native AX nodes must be nonempty");
  if (!Array.isArray(marker.steps) || marker.steps.length === 0) throw new Error("native keyboard steps must be nonempty");
  const nodeKeys = new Set();
  for (const node of marker.nodes) {
    if (!node || typeof node !== "object" || Object.keys(node).sort().join(",") !== "name,role") throw new Error("native AX node schema mismatch");
    if (!allowedRoles.has(node.role) || !allowedNames.has(node.name)) throw new Error("native AX node role/name is not allowlisted");
    const key = `${node.role}:${node.name}`;
    if (nodeKeys.has(key)) throw new Error("native AX nodes contain duplicates");
    nodeKeys.add(key);
  }
  if (!nodeKeys.has("application:Omi")) throw new Error("native AX nodes must include the Omi application");
  const stepKeys = new Set();
  for (const step of marker.steps) {
    if (!step || typeof step !== "object" || Object.keys(step).sort().join(",") !== "action,key,result") throw new Error("native keyboard step schema mismatch");
    if (typeof step.key !== "string" || !/^[a-z][a-z0-9-]{0,31}$/.test(step.key)) throw new Error("native keyboard step key is unsafe");
    if (!allowedActions.has(step.action) || !allowedResults.has(step.result)) throw new Error("native keyboard step action/result is not allowlisted");
    if (stepKeys.has(step.key)) throw new Error("native keyboard steps contain duplicate keys");
    stepKeys.add(step.key);
  }
  return marker;
}

/** Extract the one retained JSON attachment from an xcresult export directory. */
export function extractMarkerAttachment(exportDir, expected = {}) {
  const manifest = readJson(path.join(exportDir, "manifest.json"), "attachment manifest");
  if (!Array.isArray(manifest) || manifest.length !== 1) throw new Error("xcresult attachment manifest must contain one test");
  const test = manifest[0];
  if (expected.testIdentifier && test.testIdentifierURL !== expected.testIdentifier) throw new Error("xcresult test identifier mismatch");
  if (!Array.isArray(test.attachments)) throw new Error("xcresult attachment list missing");
  const markerAttachments = test.attachments.filter((item) => typeof item.suggestedHumanReadableName === "string" && item.suggestedHumanReadableName.startsWith("OMI_NATIVE_IOS_SEMANTIC_JSON"));
  if (markerAttachments.length !== 1) throw new Error(`expected exactly one native semantic attachment, found ${markerAttachments.length}`);
  const attachment = markerAttachments[0];
  if (expected.finishedEpoch !== undefined && (!Number.isFinite(attachment.timestamp) || attachment.timestamp > expected.finishedEpoch + 1)) throw new Error("native semantic attachment arrived after test completion");
  if (attachment.isAssociatedWithFailure === true) throw new Error("native semantic attachment is associated with a failed test");
  if (typeof attachment.exportedFileName !== "string" || !/^[A-Za-z0-9-]+\.json$/.test(attachment.exportedFileName)) throw new Error("native semantic attachment filename is unsafe");
  const file = path.join(exportDir, attachment.exportedFileName);
  if (!existsSync(file) || !statSync(file).isFile()) throw new Error("native semantic attachment bytes are missing");
  const bytes = readFileSync(file);
  let marker;
  try { marker = JSON.parse(bytes.toString("utf8")); } catch (error) { throw new Error(`native semantic attachment is not JSON: ${error instanceof Error ? error.message : String(error)}`); }
  return { marker: validateMarker(marker), bytes, attachment };
}

function environment() {
  const keys = ["PATH", "TMPDIR", "LANG", "LC_ALL", "DEVELOPER_DIR", "SDKROOT", "FLUTTER_BIN", "NODE_BIN"];
  const env = Object.fromEntries(keys.filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
  const scratch = path.join(coreRoot, ".build/native-ios-semantic", "home");
  mkdirSync(scratch, { recursive: true });
  env.HOME = scratch;
  env.PUB_CACHE = path.join(scratch, ".pub-cache");
  env.XDG_CACHE_HOME = path.join(scratch, ".cache");
  return env;
}

function run(command, args, options) {
  const result = spawnSync(command, args, { ...options, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], maxBuffer: 64 * 1024 * 1024 });
  if (result.error?.code === "ETIMEDOUT") throw new Error(`${path.basename(command)} timed out`);
  return result;
}

function canonicalArtifacts(manifest, marker, outDir) {
  const metadata = {
    domain: manifest.domain,
    shell: manifest.shell,
    state: manifest.state,
    theme: manifest.theme,
    width: manifest.width,
    accessibility: manifest.accessibility,
    run_id: manifest.run_id,
    source_shas: manifest.source_shas,
    capture_class: manifest.capture_class,
    source_tier: manifest.source_tier,
  };
  const ax = { schema: "omi.polish.ax/v1", ...metadata, nodes: marker.nodes };
  const keyboard = { schema: "omi.polish.keyboard/v1", ...metadata, steps: marker.steps };
  const axPath = path.join(outDir, "native-ax.json");
  const keyboardPath = path.join(outDir, "native-keyboard.json");
  const axBytes = Buffer.from(stableJson(ax));
  const keyboardBytes = Buffer.from(stableJson(keyboard));
  writeFileSync(axPath, axBytes, { mode: 0o600 });
  writeFileSync(keyboardPath, keyboardBytes, { mode: 0o600 });
  return { axPath, keyboardPath, axSha256: sha256(axBytes), keyboardSha256: sha256(keyboardBytes) };
}

export function validateMarkerForTest(marker) {
  return validateMarker(marker);
}

export function validateManifestForTest(manifest) {
  return validateManifest(manifest);
}

function main() {
  let args;
  try { args = parseArgs(process.argv.slice(2)); } catch (error) { fail(error.message); return; }
  if (args.help) {
    console.log("usage: capture-native-semantic-evidence.mjs --manifest coordinate.json [--device UDID] [--output-dir /abs/core/.build/..]");
    return;
  }
  if (!args.manifest) { fail("--manifest is required"); return; }
  const manifestPath = path.resolve(args.manifest);
  let manifest;
  try { manifest = readJson(manifestPath, "manifest"); validateManifest(manifest); } catch (error) { fail(`invalid manifest: ${error.message}`); return; }
  const sourceRoot = path.resolve(args.source_root || coreRoot);
  let currentCore;
  try { currentCore = gitHead(sourceRoot); } catch (error) { fail(error.message); return; }
  if (manifest.source_shas.core !== currentCore) { fail(`manifest core SHA ${manifest.source_shas.core} does not match current core HEAD ${currentCore}`); return; }
  const platformRoot = args.platform_root || process.env.OMI_PLATFORM_ROOT;
  if (platformRoot) {
    let currentPlatform;
    try { currentPlatform = gitHead(path.resolve(platformRoot)); } catch (error) { fail(error.message); return; }
    if (manifest.source_shas.platform !== currentPlatform) { fail(`manifest platform SHA ${manifest.source_shas.platform} does not match current platform HEAD ${currentPlatform}`); return; }
  }
  const outputDir = args.output_dir ? insideCore(args.output_dir, "--output-dir") : path.join(coreRoot, ".build/native-ios-semantic", manifest.run_id);
  mkdirSync(outputDir, { recursive: true });
  const device = args.device || "7F64F7EE-5F25-44C3-9BA1-030E0FD6CDAD";
  const surfacesDist = process.env.SURFACES_DIST;
  if (!surfacesDist || !existsSync(path.join(surfacesDist, "index.html"))) { fail("SURFACES_DIST must point to an immutable surfaces dist/index.html"); return; }
  const env = environment();
  env.SURFACES_DIST = path.resolve(surfacesDist);
  const nodeBin = env.NODE_BIN || process.execPath;
  const flutterBin = env.FLUTTER_BIN || path.join(process.env.HOME || "/Users/dazheng", ".local/share/mise/installs/flutter/3.44.5/bin/flutter");
  const query = new URLSearchParams({ qa: manifest.domain, polish: "1", state: manifest.state, theme: manifest.theme, platform: "mobile", accessibility: manifest.accessibility }).toString();
  const startedAt = new Date();
  const bundle = run(nodeBin, [path.join(iosRoot, "tools/build-surfaces-bundle.mjs")], { cwd: coreRoot, env, timeout: 120_000 });
  if (bundle.status !== 0) { fail(`surfaces bundle build failed: ${bundle.stderr || bundle.stdout}`); return; }
  const flutter = run(flutterBin, ["build", "ios", "--simulator", "--debug", `--dart-define=SURFACE_MODE=scheme`, `--dart-define=SCHEME_BUNDLE=surfaces`, `--dart-define=SURFACE_QUERY=${query}`], { cwd: path.join(iosRoot, "app"), env, timeout: 300_000 });
  if (flutter.status !== 0) { fail(`Flutter fixture build failed: ${flutter.stderr || flutter.stdout}`); return; }
  const resultBundle = path.join(outputDir, "Runner.xcresult");
  const xcodeArgs = ["test", "-project", project, "-scheme", scheme, "-destination", `platform=iOS Simulator,id=${device}`, "-only-testing", testOnly, "-parallel-testing-enabled", "NO", "-derivedDataPath", path.join(outputDir, "DerivedData"), "-resultBundlePath", resultBundle, "CODE_SIGNING_ALLOWED=NO", `FLUTTER_ROOT=${path.dirname(path.dirname(flutterBin))}`];
  const xcodeStarted = new Date();
  const xcode = run("xcodebuild", xcodeArgs, { cwd: path.join(iosRoot, "app"), env, timeout: 300_000 });
  const finishedAt = new Date();
  if (xcode.status !== 0) { fail(`xcodebuild semantic test failed (exit ${xcode.status ?? "signal"})`); return; }
  const exportDir = path.join(outputDir, "attachments");
  mkdirSync(exportDir, { recursive: true });
  const exported = run("xcrun", ["xcresulttool", "export", "attachments", "--path", resultBundle, "--output-path", exportDir, "--test-id", testIdentifier], { cwd: coreRoot, env, timeout: 30_000 });
  if (exported.status !== 0) { fail(`xcresult attachment export failed: ${exported.stderr || exported.stdout}`); return; }
  let native;
  try { native = extractMarkerAttachment(exportDir, { testIdentifier, finishedEpoch: finishedAt.getTime() / 1000 }); } catch (error) { fail(error.message); return; }
  const artifacts = canonicalArtifacts(manifest, native.marker, outputDir);
  const receipt = {
    schema: "omi.polish.native-ios-semantic/v1",
    run_id: manifest.run_id,
    coordinate: { domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme, width: manifest.width, accessibility: manifest.accessibility },
    capture_class: manifest.capture_class,
    source_tier: manifest.source_tier,
    source_shas: manifest.source_shas,
    surface_query: query,
    viewport: manifest.viewport,
    marker_sha256: sha256(native.bytes),
    artifact_hashes: { ax: artifacts.axSha256, keyboard: artifacts.keyboardSha256 },
    xcresult_path: path.relative(coreRoot, resultBundle),
    command: { argv: ["xcodebuild", ...xcodeArgs], cwd: path.relative(coreRoot, path.join(iosRoot, "app")), exit_code: xcode.status, started_at: xcodeStarted.toISOString(), finished_at: finishedAt.toISOString(), timeout_seconds: 300 },
    stdout_sha256: sha256(Buffer.from(xcode.stdout || "")),
    stderr_sha256: sha256(Buffer.from(xcode.stderr || "")),
    build_commands: { surfaces: [nodeBin, path.join(iosRoot, "tools/build-surfaces-bundle.mjs")], flutter: [flutterBin, ...["build", "ios", "--simulator", "--debug", `--dart-define=SURFACE_MODE=scheme`, `--dart-define=SCHEME_BUNDLE=surfaces`, `--dart-define=SURFACE_QUERY=${query}`]] },
  };
  const receiptPath = path.join(outputDir, "native-receipt.json");
  writeFileSync(receiptPath, stableJson(receipt), { mode: 0o600 });
  console.log(`NATIVE_SEMANTIC_EVIDENCE: run_id=${manifest.run_id} ax=${path.relative(coreRoot, artifacts.axPath)} keyboard=${path.relative(coreRoot, artifacts.keyboardPath)} receipt=${path.relative(coreRoot, receiptPath)}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  try { main(); } catch (error) { fail(error instanceof Error ? error.message : String(error)); }
}
