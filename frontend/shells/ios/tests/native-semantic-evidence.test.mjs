import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { canonicalArtifactsForTest, extractMarkerAttachment, gateReplayForTest, validateManifestForTest, validateMarkerForTest, validateMatrixMarkerForTest } from "../tools/capture-native-semantic-evidence.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const producer = path.join(here, "../tools/capture-native-semantic-evidence.mjs");
const testIdentifier = "test://com.apple.xcode/Runner/RunnerUITests/NativeSemanticEvidenceUITests/testChatReadySemanticEvidence";
const validManifest = {
  schema: "omi.native-ios-semantic-supplementary/v1", kind: "supplementary_semantic", domain: "chat", shell: "ios", state: "ready", theme: "light", width: "compact", accessibility: "none", run_id: "native-semantic-test", capture_class: "native_fixture", source_tier: "native_shell",
  source_shas: { core: "1".repeat(40), platform: "2".repeat(40) }, viewport: { width: 402, height: 874, scale: 3 },
};

const validAxManifest = {
  ...validManifest,
  schema: "omi.polish.matrix-coordinate/v1",
  kind: "ax_snapshot",
  width: "regular",
  accessibility: "voiceover",
  run_id: "native-ax-test",
  viewport: { width: 834, height: 1194, scale: 3 },
};

const validKeyboardManifest = {
  ...validManifest,
  schema: "omi.polish.matrix-coordinate/v1",
  kind: "keyboard_trace",
  accessibility: "keyboard",
  run_id: "native-keyboard-test",
};

function marker(overrides = {}) {
  return {
    schema: "omi.native-ios-semantic-marker.v1",
    bundleId: "me.omi.proto.omiWebviewProto",
    nodes: [
      { role: "application", name: "Omi" },
      { role: "web-view", name: "Omi surface" },
    ],
    steps: [
      { key: "launch", action: "launch", result: "foreground" },
      { key: "tap", action: "tap", result: "web-view-accepted" },
    ],
    ...overrides,
  };
}

function matrixMarker(overrides = {}) {
  return marker({
    nodes: [
      { role: "application", name: "Omi" },
      { role: "web-view", name: "Omi surface" },
      { role: "static-text", name: "Chat" },
    ],
    ...overrides,
  });
}

test("native iOS semantic marker accepts only strict redacted records", () => {
  assert.deepEqual(validateMarkerForTest(marker()).nodes.length, 2);
  for (const hostile of [
    { ...marker(), secret: "credential" },
    { ...marker(), nodes: [{ role: "application", name: "Omi", value: "user text" }] },
    { ...marker(), nodes: [{ role: "application", name: "Omi" }, { role: "button", name: "Raw user text" }] },
    { ...marker(), nodes: [{ role: "application", name: "Omi" }, { role: "web-view", name: "Omi surface" }, { role: "web-view", name: "Omi surface" }] },
    { ...marker(), steps: [{ key: "tap", action: "tap", result: "accepted" }, { key: "tap", action: "tap", result: "accepted" }] },
  ]) {
    assert.throws(() => validateMarkerForTest(hostile));
  }
});

test("native iOS coordinate manifests reject extra metadata and malformed nested keys", () => {
  assert.doesNotThrow(() => validateManifestForTest(validManifest));
  assert.throws(() => validateManifestForTest({ ...validManifest, secret: "token" }), /unexpected or missing keys/);
  assert.throws(() => validateManifestForTest({ ...validManifest, viewport: { ...validManifest.viewport, secret: 1 } }), /bounded logical width/);
  assert.throws(() => validateManifestForTest({ ...validManifest, source_shas: { ...validManifest.source_shas, extra: "x" } }), /full SHAs/);
});

test("matrix manifests are exact typed coordinates and supplementary proof is explicit", () => {
  assert.deepEqual(validateManifestForTest(validManifest), { matrix: false, supplementary: true });
  assert.deepEqual(validateManifestForTest(validAxManifest), { matrix: true, supplementary: false });
  assert.deepEqual(validateManifestForTest(validKeyboardManifest), { matrix: true, supplementary: false });
  assert.throws(() => validateManifestForTest({ ...validManifest, schema: "omi.polish.matrix-coordinate/v1", kind: "semantic" }), /exact matrix/);
  assert.throws(() => validateManifestForTest({ ...validAxManifest, accessibility: "none" }), /six explicit accessibility/);
  assert.throws(() => validateManifestForTest({ ...validKeyboardManifest, accessibility: "voiceover" }), /accessibility=keyboard/);
  assert.throws(() => validateManifestForTest({ ...validAxManifest, width: "compact" }), /regular logical viewport/);
  for (const fixture of ["../fixtures/native-ax-chat-ready-voiceover.json", "../fixtures/native-keyboard-chat-ready.json"]) {
    const manifest = JSON.parse(readFileSync(path.join(here, fixture), "utf8"));
    assert.deepEqual(validateManifestForTest(manifest), { matrix: true, supplementary: false });
  }
});

test("matrix AX requires a domain landmark and keyboard requires observed transition", () => {
  assert.doesNotThrow(() => validateMatrixMarkerForTest(matrixMarker(), validAxManifest));
  assert.throws(() => validateMatrixMarkerForTest(marker(), validAxManifest), /domain landmark/);
  assert.throws(() => validateMatrixMarkerForTest(matrixMarker(), validKeyboardManifest), /real key action/);
  assert.doesNotThrow(() => validateMatrixMarkerForTest(matrixMarker({
    steps: [
      { key: "launch", action: "launch", result: "foreground" },
      { key: "focus", action: "tap", result: "keyboard-visible" },
      { key: "type-text", action: "typeText", result: "accepted" },
      { key: "shift-command-p", action: "typeKey", result: "transition-observed" },
      { key: "escape", action: "typeKey", result: "restored" },
    ],
  }), validKeyboardManifest));
});

test("supplementary WebView proof cannot emit a keyboard-trace artifact", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-semantic-artifacts-"));
  const artifacts = canonicalArtifactsForTest(validManifest, marker(), scratch, { matrix: false, supplementary: true });
  assert.ok(artifacts.axPath.endsWith("supplementary-ax.json"));
  assert.equal(artifacts.keyboardPath, undefined);
});

test("prepared matrix AX replay emits gate-shaped input-set and batch receipt", () => {
  const replayParent = path.join(here, "../.build");
  mkdirSync(replayParent, { recursive: true });
  const rootScratch = mkdtempSync(path.join(replayParent, "native-semantic-replay-"));
  const currentCore = spawnSync("git", ["rev-parse", "HEAD"], { cwd: path.resolve(here, "../../.."), encoding: "utf8" }).stdout.trim();
  const manifest = { ...validAxManifest, source_shas: { core: currentCore, platform: "2".repeat(40) } };
  const manifestPath = path.join(rootScratch, "manifest.json");
  const inputPath = path.join(rootScratch, "prepared-ax.json");
  const outputPath = path.join(rootScratch, "replayed-ax.json");
  const document = { schema: "omi.polish.ax/v1", domain: manifest.domain, shell: manifest.shell, state: manifest.state, theme: manifest.theme, width: manifest.width, accessibility: manifest.accessibility, run_id: manifest.run_id, source_shas: manifest.source_shas, capture_class: manifest.capture_class, source_tier: manifest.source_tier, nodes: matrixMarker().nodes };
  try {
    writeFileSync(manifestPath, JSON.stringify(manifest));
    const inputBytes = Buffer.from(JSON.stringify(document) + "\n");
    writeFileSync(inputPath, inputBytes);
    writeFileSync(path.join(rootScratch, "native-preparation-receipt.json"), JSON.stringify({
      schema: "omi.polish.native-ios-preparation/v1",
      run_id: manifest.run_id,
      source_shas: manifest.source_shas,
      capture_class: manifest.capture_class,
      source_tier: manifest.source_tier,
      artifact_hashes: { ax: createHash("sha256").update(inputBytes).digest("hex") },
      foreground_custody: {
        schema: "omi.macos-foreground-guard/v1", status: 0, signal: null, error: null, monitor_error: null,
        target_interval_milliseconds: 20, probe_timeout_milliseconds: 250, sample_count: 2,
        max_sample_gap_milliseconds: 20,
        forbidden_bundle_ids: ["com.apple.iphonesimulator", "me.omi.proto.omiWebviewProto"],
        policy: "sampled-macos-forbidden-fixture-foreground-detection-20ms-target-250ms-probe-timeout-no-activation-request",
      },
    }));
    const result = gateReplayForTest(manifest, manifestPath, inputPath, outputPath, rootScratch);
    assert.equal(result.receipt.cwd_root, "core");
    const coreRootForTest = path.resolve(here, "../../..");
    assert.equal(result.receipt.batch_members.m0.evidence.path, path.relative(coreRootForTest, outputPath));
    assert.ok(result.receipt.input_set.id.startsWith("input-v1-"));
    assert.ok(result.receipt.input_set.entries.some((entry) => entry.key.endsWith("native-preparation-receipt.json")));
    assert.ok(result.receipt.input_set.entries.some((entry) => entry.key.endsWith("macos-foreground-guard.mjs")));
    assert.equal(result.receipt.artifact_created[`core:${path.relative(coreRootForTest, outputPath)}`], true);
    assert.match(readFileSync(result.coveragePath, "utf8"), /batch_member/);
    rmSync(outputPath, { force: true });
    const replay = spawnSync(result.receipt.argv[0], result.receipt.argv.slice(1), { cwd: coreRootForTest, encoding: "utf8" });
    assert.equal(replay.status, 0, replay.stderr);
    assert.equal(createHash("sha256").update(replay.stdout).digest("hex"), result.receipt.stdout_sha256);
    const preparationPath = path.join(rootScratch, "native-preparation-receipt.json");
    const preparation = JSON.parse(readFileSync(preparationPath, "utf8"));
    writeFileSync(preparationPath, JSON.stringify({ ...preparation, foreground_custody: { ...preparation.foreground_custody, monitor_error: "changed" } }));
    assert.throws(() => gateReplayForTest(manifest, manifestPath, inputPath, path.join(rootScratch, "tampered.json"), rootScratch), /foreground custody/);
  } finally {
    rmSync(rootScratch, { recursive: true, force: true });
  }
});

test("xcresult extraction rejects duplicate, late, and cursor-mismatched attachments", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-semantic-"));
  const bytes = Buffer.from(JSON.stringify(marker()));
  writeFileSync(path.join(scratch, "one.json"), bytes);
  writeFileSync(path.join(scratch, "two.json"), bytes);
  const manifest = (attachments) => [{ testIdentifier: "NativeSemanticEvidenceUITests/testChatReadySemanticEvidence()", testIdentifierURL: testIdentifier, attachments }];
  writeFileSync(path.join(scratch, "manifest.json"), JSON.stringify(manifest([{ exportedFileName: "one.json", suggestedHumanReadableName: "OMI_NATIVE_IOS_SEMANTIC_JSON_0.json", timestamp: 100 }])));
  assert.equal(extractMarkerAttachment(scratch, { testIdentifier, finishedEpoch: 100 }).marker.schema, "omi.native-ios-semantic-marker.v1");
  writeFileSync(path.join(scratch, "manifest.json"), JSON.stringify(manifest([
    { exportedFileName: "one.json", suggestedHumanReadableName: "OMI_NATIVE_IOS_SEMANTIC_JSON_0.json", timestamp: 100 },
    { exportedFileName: "two.json", suggestedHumanReadableName: "OMI_NATIVE_IOS_SEMANTIC_JSON_1.json", timestamp: 100 },
  ])));
  assert.throws(() => extractMarkerAttachment(scratch, { testIdentifier, finishedEpoch: 100 }), /exactly one/);
  writeFileSync(path.join(scratch, "manifest.json"), JSON.stringify(manifest([{ exportedFileName: "one.json", suggestedHumanReadableName: "OMI_NATIVE_IOS_SEMANTIC_JSON_0.json", timestamp: 102 }] )));
  assert.throws(() => extractMarkerAttachment(scratch, { testIdentifier, finishedEpoch: 100 }), /after test completion/);
  writeFileSync(path.join(scratch, "manifest.json"), JSON.stringify(manifest([{ exportedFileName: "one.json", suggestedHumanReadableName: "OMI_NATIVE_IOS_SEMANTIC_JSON_0.json", timestamp: 100 }] ).map((entry) => ({ ...entry, testIdentifierURL: `${testIdentifier}-cursor` }))));
  assert.throws(() => extractMarkerAttachment(scratch, { testIdentifier, finishedEpoch: 100 }), /identifier mismatch/);
});

test("native semantic wrapper has explicit credential-free environment and no browser shortcut", () => {
  const source = readFileSync(producer, "utf8");
  assert.match(source, /allowedRoles/);
  assert.match(source, /capture_class !== "native_fixture"/);
  assert.match(source, /xcresulttool/);
  assert.match(source, /exportMarkerAttachment|extractMarkerAttachment/);
  assert.match(source, /const keys = \["PATH"/);
  assert.doesNotMatch(source, /\.\.\.process\.env/);
  assert.doesNotMatch(source, /OMI_API_TOKEN|OMI_API_BASE_URL/);
  assert.match(source, /parallel-testing-enabled/);
  assert.match(source, /testIdentifier/);
  assert.match(source, /platform_root|OMI_PLATFORM_ROOT/);
  assert.match(source, /source_root/);
  assert.match(source, /macos-foreground-guard\.mjs/);
  assert.match(source, /foreground_custody/);
  assert.match(source, /monitor_error !== null/);
});
