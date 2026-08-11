import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { extractMarkerAttachment, validateManifestForTest, validateMarkerForTest } from "../tools/capture-native-semantic-evidence.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const producer = path.join(here, "../tools/capture-native-semantic-evidence.mjs");
const testIdentifier = "test://com.apple.xcode/Runner/RunnerUITests/NativeSemanticEvidenceUITests/testChatReadySemanticEvidence";
const validManifest = {
  schema: "omi.polish.matrix-coordinate/v1", kind: "semantic", domain: "chat", shell: "ios", state: "ready", theme: "light", width: "compact", accessibility: "none", run_id: "native-semantic-test", capture_class: "native_fixture", source_tier: "native_shell",
  source_shas: { core: "1".repeat(40), platform: "2".repeat(40) }, viewport: { width: 1206, height: 2622, scale: 3 },
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
  assert.throws(() => validateManifestForTest({ ...validManifest, viewport: { ...validManifest.viewport, secret: 1 } }), /bounded width/);
  assert.throws(() => validateManifestForTest({ ...validManifest, source_shas: { ...validManifest.source_shas, extra: "x" } }), /full SHAs/);
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
});
