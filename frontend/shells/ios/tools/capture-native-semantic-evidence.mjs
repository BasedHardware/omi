#!/usr/bin/env node
/**
 * Run the fixture-only iOS UI-test target and turn its one JSON attachment into
 * verifier-owned AX and keyboard artifacts.  The test target never receives
 * credentials or arbitrary user text; this wrapper binds the exact coordinate,
 * source SHAs, capture class, run id and xcodebuild receipt around the native
 * result bundle.
 */
import { createHash } from "node:crypto";
import { existsSync, lstatSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const iosRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const coreRoot = path.resolve(iosRoot, "../..");
const project = path.join(iosRoot, "app/ios/Runner.xcodeproj");
const scheme = "Runner";
const testIdentifier = "test://com.apple.xcode/Runner/RunnerUITests/NativeSemanticEvidenceUITests/testChatReadySemanticEvidence";
const testOnly = "RunnerUITests/NativeSemanticEvidenceUITests/testChatReadySemanticEvidence";
const foregroundGuard = path.join(coreRoot, "shells/tools/macos-foreground-guard.mjs");
const domains = new Set(["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"]);
const states = new Set(["loading", "empty", "ready", "error", "offline", "busy", "complete", "cancelled"]);
const themes = new Set(["light", "dark"]);
const widths = new Set(["compact", "regular", "wide"]);
const accessibilities = new Set(["none", "keyboard", "voiceover", "high_contrast", "reduced_motion", "reduced_transparency", "rtl", "text_scale_200"]);
const matrixKinds = new Set(["ax_snapshot", "keyboard_trace"]);
const matrixAxAccessibilities = new Set(["voiceover", "high_contrast", "reduced_motion", "reduced_transparency", "rtl", "text_scale_200"]);
const supplementarySchema = "omi.native-ios-semantic-supplementary/v1";
const safeId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const sha = /^[0-9a-f]{40}$/;
const allowedRoles = new Set(["application", "web-view", "button", "text-field", "static-text"]);
const allowedNames = new Set(["Omi", "Omi surface", "Memories", "Tasks", "Conversations", "Folders", "Listen", "Chat", "Settings", "Search", "Send", "Close", "Cancel", "Try again", "All Conversations"]);
const allowedActions = new Set(["launch", "tap", "typeText", "typeKey"]);
const allowedResults = new Set(["foreground", "accepted", "web-view-accepted", "keyboard-visible", "keyboard-not-observed", "sent", "transition-observed", "restored"]);

function stableJson(value) {
  return `${JSON.stringify(value)}\n`;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalValue(value[key])]));
  return value;
}

function canonicalHash(value) {
  return sha256(Buffer.from(JSON.stringify(canonicalValue(value))));
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
  const supplementary = manifest?.schema === supplementarySchema && manifest?.kind === "supplementary_semantic";
  const matrix = manifest?.schema === "omi.polish.matrix-coordinate/v1" && matrixKinds.has(manifest?.kind);
  if (!supplementary && !matrix) throw new Error("manifest must be an exact matrix ax_snapshot/keyboard_trace coordinate or an explicitly supplementary semantic manifest");
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
  if (!manifest.viewport || typeof manifest.viewport !== "object" || Object.keys(manifest.viewport).sort().join(",") !== "height,scale,width" || !Number.isInteger(manifest.viewport.width) || !Number.isInteger(manifest.viewport.height) || !Number.isFinite(manifest.viewport.scale) || manifest.viewport.width < 320 || manifest.viewport.width > 2400 || manifest.viewport.height < 320 || manifest.viewport.height > 2800 || manifest.viewport.scale <= 0 || manifest.viewport.scale > 4) throw new Error("viewport must contain bounded logical width, height and scale");
  if (supplementary && manifest.accessibility !== "none") throw new Error("supplementary semantic fixtures must use accessibility=none");
  if (matrix && manifest.kind === "ax_snapshot" && !matrixAxAccessibilities.has(manifest.accessibility)) throw new Error("ax_snapshot requires one of the six explicit accessibility modes");
  if (matrix && manifest.kind === "keyboard_trace" && manifest.accessibility !== "keyboard") throw new Error("keyboard_trace requires accessibility=keyboard");
  if (matrix && manifest.kind === "ax_snapshot" && manifest.width !== "regular") throw new Error("ax_snapshot matrix coordinates use the regular logical viewport");
  return { matrix, supplementary };
}

function domainNames(domain) {
  return {
    memories: new Set(["Memories"]),
    tasks: new Set(["Tasks"]),
    conversations: new Set(["Conversations", "All Conversations"]),
    folders: new Set(["Folders"]),
    chat: new Set(["Chat", "Send", "Search"]),
    listen: new Set(["Listen"]),
    settings: new Set(["Settings"]),
  }[domain] || new Set();
}

function validateMatrixMarker(marker, manifest) {
  validateMarker(marker);
  const allowed = domainNames(manifest.domain);
  if (!marker.nodes.some((node) => allowed.has(node.name))) throw new Error(`native AX nodes must include an allowlisted ${manifest.domain} domain landmark/action`);
  if (manifest.kind === "keyboard_trace") {
    validateKeyboardSteps(marker.steps);
  }
  return marker;
}

function validateKeyboardSteps(steps) {
  const keys = new Map(steps.map((step) => [step.key, step]));
  if (keys.get("type-text")?.result !== "accepted" || keys.get("shift-command-p")?.result !== "transition-observed" || keys.get("escape")?.result !== "restored") throw new Error("keyboard_trace requires a real key action with observed transition and restoration");
}

function hasObservedKeyboardTransition(marker) {
  const steps = new Map(marker.steps.map((step) => [step.key, step]));
  return steps.get("type-text")?.result === "accepted"
    && steps.get("shift-command-p")?.result === "transition-observed"
    && steps.get("escape")?.result === "restored";
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

function runForegroundGuarded(command, args, options, outputDir) {
  const guardResult = path.join(outputDir, "foreground-guard.json");
  const stdoutPath = path.join(outputDir, "xcodebuild.stdout");
  const stderrPath = path.join(outputDir, "xcodebuild.stderr");
  const wrapped = spawnSync(process.execPath, [foregroundGuard, "--result", guardResult, "--stdout", stdoutPath, "--stderr", stderrPath, "--timeout", "300", "--", command, ...args], { ...options, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], maxBuffer: 16 * 1024 * 1024 });
  if (!existsSync(guardResult)) throw new Error("iOS semantic foreground guard produced no terminal receipt");
  const custody = readJson(guardResult, "iOS semantic foreground guard");
  if (custody.schema !== "omi.macos-foreground-guard/v1" || custody.monitor_error !== null || custody.error !== null || custody.status !== 0) throw new Error(`iOS semantic foreground custody failed: ${custody.monitor_error || custody.error || custody.status}`);
  if (wrapped.status !== 0) throw new Error("iOS semantic foreground guard failed");
  return { status: custody.status, stdout: readFileSync(stdoutPath, "utf8"), stderr: readFileSync(stderrPath, "utf8"), custody };
}

function relativeCore(file, label) {
  const resolved = insideCore(file, label);
  const relative = path.relative(coreRoot, resolved);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error(`${label} must be inside the core worktree`);
  return { resolved, relative };
}

function inputEntry(file, relative) {
  const info = lstatSync(file);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error("replay input must be a regular file, not a symlink");
  const bytes = readFileSync(file);
  return { key: `core:${relative}`, sha256: sha256(bytes), size: bytes.length, mode: info.mode & 0o777 };
}

function gateReplay(manifest, manifestPath, inputPath, outputPath, outDir, emitRecords = true) {
  const manifestLocation = relativeCore(manifestPath, "--manifest");
  const input = relativeCore(inputPath, "--replay-input");
  const output = relativeCore(outputPath, "--replay-output");
  if (input.resolved === output.resolved) throw new Error("--replay-output must differ from --replay-input");
  const inputBytes = readFileSync(input.resolved);
  const document = readJson(input.resolved, "replay input");
  const expectedSchema = manifest.kind === "ax_snapshot" ? "omi.polish.ax/v1" : "omi.polish.keyboard/v1";
  if (document.schema !== expectedSchema) throw new Error(`replay input schema must be ${expectedSchema}`);
  const metadata = { domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme, width: manifest.width, accessibility: manifest.accessibility, run_id: manifest.run_id, source_shas: manifest.source_shas, capture_class: manifest.capture_class, source_tier: manifest.source_tier };
  for (const [key, value] of Object.entries(metadata)) if (JSON.stringify(document[key]) !== JSON.stringify(value)) throw new Error(`replay input metadata ${key} does not match manifest`);
  if (manifest.kind === "ax_snapshot") {
    if (Object.keys(document).sort().join(",") !== [...Object.keys(metadata), "nodes", "schema"].sort().join(",")) throw new Error("replay AX artifact has unexpected keys");
    validateMatrixMarker({ schema: "omi.native-ios-semantic-marker.v1", bundleId: "me.omi.proto.omiWebviewProto", nodes: document.nodes, steps: [{ key: "launch", action: "launch", result: "foreground" }] }, manifest);
  } else {
    if (Object.keys(document).sort().join(",") !== [...Object.keys(metadata), "steps", "schema"].sort().join(",")) throw new Error("replay keyboard artifact has unexpected keys");
    validateKeyboardSteps(document.steps);
  }
  mkdirSync(path.dirname(output.resolved), { recursive: true });
  writeFileSync(output.resolved, inputBytes, { mode: 0o600, flag: "wx" });
  const outputBytes = readFileSync(output.resolved);
  const scriptLocation = relativeCore(path.resolve(fileURLToPath(import.meta.url)), "producer script");
  const sourceEntry = inputEntry(input.resolved, input.relative);
  const manifestEntry = inputEntry(manifestLocation.resolved, manifestLocation.relative);
  const scriptEntry = inputEntry(scriptLocation.resolved, scriptLocation.relative);
  const outputHash = sha256(outputBytes);
  const inputSet = { entries: [manifestEntry, scriptEntry, sourceEntry].sort((left, right) => left.key.localeCompare(right.key)) };
  inputSet.tree_sha256 = canonicalHash(inputSet.entries);
  inputSet.id = `input-v1-${inputSet.tree_sha256}`;
  const command = `node ${path.relative(coreRoot, path.resolve(fileURLToPath(import.meta.url)))} --manifest ${manifestLocation.relative} --replay-input ${input.relative} --replay-output ${output.relative} --emit-gate-records false`;
  const member = { coordinate: [manifest.kind, manifest.domain, manifest.shell, manifest.state, manifest.theme, manifest.width, manifest.accessibility], run_id: manifest.run_id, evidence: { root: "core", path: output.relative, sha256: outputHash }, sidecar: null };
  const batchMembers = { m0: member };
  const batchId = `batch-v1-${canonicalHash({ command, input_set_id: inputSet.id, members: batchMembers })}`;
  const now = new Date().toISOString();
  const replayOutput = `NATIVE_SEMANTIC_REPLAY: kind=${manifest.kind} path=${output.relative}`;
  const receipt = {
    argv: ["node", path.relative(coreRoot, path.resolve(fileURLToPath(import.meta.url))), "--manifest", manifestLocation.relative, "--replay-input", input.relative, "--replay-output", output.relative, "--emit-gate-records", "false"],
    cwd: ".", cwd_root: "core", exit_code: 0, timeout_seconds: 30, started_at: now, finished_at: now,
    run_id: batchId, source_shas: manifest.source_shas, stdout_sha256: sha256(Buffer.from(`${replayOutput}\n`)), stderr_sha256: sha256(Buffer.from("")),
    artifact_hashes: { [`core:${output.relative}`]: outputHash }, artifact_before_hashes: { [`core:${output.relative}`]: null }, artifact_created: { [`core:${output.relative}`]: true },
    capture_class: manifest.capture_class, source_tier: manifest.source_tier, input_set: inputSet, batch_id: batchId, batch_members: batchMembers,
  };
  const receiptPath = path.join(outDir, "native-gate-command-receipt.json");
  const coveragePath = path.join(outDir, "native-gate-coverage.json");
  if (emitRecords) {
    writeFileSync(receiptPath, stableJson(receipt), { mode: 0o600 });
    writeFileSync(coveragePath, stableJson({ coverage: [{ kind: manifest.kind, domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme, width: manifest.width, accessibility: manifest.accessibility, capture_class: manifest.capture_class, source_tier: manifest.source_tier, root: "core", path: output.relative, sha256: outputHash, command, command_ran: true, command_receipt: receipt, run_id: manifest.run_id, sidecar: null, source_shas: manifest.source_shas, input_set_id: inputSet.id, batch_id: batchId, batch_member: "m0" }] }), { mode: 0o600 });
  }
  console.log(replayOutput);
  return { receiptPath, coveragePath, receipt };
}

export function gateReplayForTest(manifest, manifestPath, inputPath, outputPath, outDir) {
  return gateReplay(manifest, manifestPath, inputPath, outputPath, outDir);
}

function canonicalArtifacts(manifest, marker, outDir, mode) {
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
  const artifacts = {};
  if (mode.matrix && manifest.kind === "ax_snapshot") {
    const ax = { schema: "omi.polish.ax/v1", ...metadata, nodes: marker.nodes };
    const axPath = path.join(outDir, "matrix-ax.json");
    const axBytes = Buffer.from(stableJson(ax));
    writeFileSync(axPath, axBytes, { mode: 0o600 });
    artifacts.axPath = axPath;
    artifacts.axSha256 = sha256(axBytes);
  } else if (mode.matrix && manifest.kind === "keyboard_trace") {
    const keyboard = { schema: "omi.polish.keyboard/v1", ...metadata, steps: marker.steps };
    const keyboardPath = path.join(outDir, "matrix-keyboard.json");
    const keyboardBytes = Buffer.from(stableJson(keyboard));
    writeFileSync(keyboardPath, keyboardBytes, { mode: 0o600 });
    artifacts.keyboardPath = keyboardPath;
    artifacts.keyboardSha256 = sha256(keyboardBytes);
  } else {
    // Supplementary output is intentionally kept out of the matrix naming
    // convention so a coordinator cannot accidentally close a required row.
    const ax = { schema: "omi.native-ios-ax-supplementary/v1", ...metadata, nodes: marker.nodes };
    const axPath = path.join(outDir, "supplementary-ax.json");
    const axBytes = Buffer.from(stableJson(ax));
    writeFileSync(axPath, axBytes, { mode: 0o600 });
    artifacts.axPath = axPath;
    artifacts.axSha256 = sha256(axBytes);
    if (hasObservedKeyboardTransition(marker)) {
      const keyboard = { schema: "omi.native-ios-keyboard-supplementary/v1", ...metadata, steps: marker.steps };
      const keyboardPath = path.join(outDir, "supplementary-keyboard.json");
      const keyboardBytes = Buffer.from(stableJson(keyboard));
      writeFileSync(keyboardPath, keyboardBytes, { mode: 0o600 });
      artifacts.keyboardPath = keyboardPath;
      artifacts.keyboardSha256 = sha256(keyboardBytes);
    }
  }
  return artifacts;
}

export function canonicalArtifactsForTest(manifest, marker, outDir, mode) {
  return canonicalArtifacts(manifest, marker, outDir, mode);
}

export function validateMarkerForTest(marker) {
  return validateMarker(marker);
}

export function validateMatrixMarkerForTest(marker, manifest) {
  return validateMatrixMarker(marker, manifest);
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
  let mode;
  try { manifest = readJson(manifestPath, "manifest"); mode = validateManifest(manifest); } catch (error) { fail(`invalid manifest: ${error.message}`); return; }
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
  if (args.replay_input || args.replay_output) {
    if (!mode.matrix) { fail("--replay-input/--replay-output require an exact matrix manifest"); return; }
    if (!args.replay_input || !args.replay_output) { fail("--replay-input and --replay-output must be provided together"); return; }
    try { gateReplay(manifest, manifestPath, path.resolve(args.replay_input), path.resolve(args.replay_output), outputDir, args.emit_gate_records !== "false"); } catch (error) { fail(error instanceof Error ? error.message : String(error)); }
    return;
  }
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
  let xcode;
  try { xcode = runForegroundGuarded("xcodebuild", xcodeArgs, { cwd: path.join(iosRoot, "app"), env }, outputDir); }
  catch (error) { fail(error.message); return; }
  const finishedAt = new Date();
  if (xcode.status !== 0) { fail(`xcodebuild semantic test failed (exit ${xcode.status ?? "signal"})`); return; }
  const exportDir = path.join(outputDir, "attachments");
  mkdirSync(exportDir, { recursive: true });
  const exported = run("xcrun", ["xcresulttool", "export", "attachments", "--path", resultBundle, "--output-path", exportDir, "--test-id", testIdentifier], { cwd: coreRoot, env, timeout: 30_000 });
  if (exported.status !== 0) { fail(`xcresult attachment export failed: ${exported.stderr || exported.stdout}`); return; }
  let native;
  try {
    native = extractMarkerAttachment(exportDir, { testIdentifier, finishedEpoch: finishedAt.getTime() / 1000 });
    if (mode.matrix) validateMatrixMarker(native.marker, manifest);
  } catch (error) { fail(error.message); return; }
  const artifacts = canonicalArtifacts(manifest, native.marker, outputDir, mode);
  const receipt = {
    schema: mode.matrix ? "omi.polish.native-ios-preparation/v1" : "omi.native-ios-semantic-supplementary-receipt/v1",
    run_id: manifest.run_id,
    coordinate: { domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme, width: manifest.width, accessibility: manifest.accessibility },
    capture_class: manifest.capture_class,
    source_tier: manifest.source_tier,
    source_shas: manifest.source_shas,
    surface_query: query,
    viewport: manifest.viewport,
    marker_sha256: sha256(native.bytes),
    artifact_hashes: Object.fromEntries([
      artifacts.axPath && ["ax", artifacts.axSha256],
      artifacts.keyboardPath && ["keyboard", artifacts.keyboardSha256],
    ].filter(Boolean)),
    xcresult_path: path.relative(coreRoot, resultBundle),
    command: { argv: ["xcodebuild", ...xcodeArgs], cwd: path.relative(coreRoot, path.join(iosRoot, "app")), exit_code: xcode.status, started_at: xcodeStarted.toISOString(), finished_at: finishedAt.toISOString(), timeout_seconds: 300 },
    stdout_sha256: sha256(Buffer.from(xcode.stdout || "")),
    stderr_sha256: sha256(Buffer.from(xcode.stderr || "")),
    foreground_custody: xcode.custody,
    build_commands: { surfaces: [nodeBin, path.join(iosRoot, "tools/build-surfaces-bundle.mjs")], flutter: [flutterBin, ...["build", "ios", "--simulator", "--debug", `--dart-define=SURFACE_MODE=scheme`, `--dart-define=SCHEME_BUNDLE=surfaces`, `--dart-define=SURFACE_QUERY=${query}`]] },
  };
  const receiptPath = path.join(outputDir, mode.matrix ? "native-preparation-receipt.json" : "supplementary-receipt.json");
  writeFileSync(receiptPath, stableJson(receipt), { mode: 0o600 });
  console.log(`NATIVE_SEMANTIC_EVIDENCE: run_id=${manifest.run_id} mode=${mode.matrix ? "matrix" : "supplementary"} ${artifacts.axPath ? `ax=${path.relative(coreRoot, artifacts.axPath)}` : ""} ${artifacts.keyboardPath ? `keyboard=${path.relative(coreRoot, artifacts.keyboardPath)}` : ""} receipt=${path.relative(coreRoot, receiptPath)}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  try { main(); } catch (error) { fail(error instanceof Error ? error.message : String(error)); }
}
