import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { deflateSync } from "node:zlib";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const producer = path.join(root, "shells/tools/capture-native-fixture-batch.mjs");
const { assertForegroundMonitorCompletionForTest, assertMacForegroundProbeTransitionForTest, canonicalizeScreenshotForTest, nativeFocusPolicyForTest } = await import(producer);
const coreSha = execFileSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const platformSha = "1".repeat(40);

function coordinate(shell, runId, overrides = {}) {
  const width = overrides.width || (shell === "macos" ? "regular" : "compact");
  const viewport = shell === "macos"
    ? { compact: { width: 760, height: 671, scale: 2 }, regular: { width: 960, height: 671, scale: 2 }, wide: { width: 1280, height: 800, scale: 2 } }[width]
    : { compact: { width: 402, height: 874, scale: 3 }, regular: { width: 820, height: 1180, scale: 2 }, wide: { width: 1032, height: 1376, scale: 2 } }[width];
  const domain = "memories";
  const state = "ready";
  const theme = "light";
  const accessibility = "none";
  const platform = shell === "macos" ? "desktop" : "mobile";
  return {
    schema: "omi.polish.matrix-coordinate/v1", kind: "screenshot", domain, shell, state, theme, width, accessibility,
    run_id: runId, capture_class: "native_fixture", source_tier: "native_shell", source_shas: { core: coreSha, platform: platformSha },
    surface_query: `polish=1&qa=${domain === "memories" ? "memories-platform" : domain}&state=${state}&platform=${platform}&theme=${theme}&width=${width}&accessibility=${accessibility}&locale=en-US`,
    device: { udid: shell === "ios" ? "ios-udid-1" : "macos-host-1", model: shell === "ios" ? "iPhone 17 Pro" : "MacBookPro", orientation: shell === "ios" ? "portrait" : "landscape" },
    viewport, ...overrides,
  };
}

function manifest(coordinates) {
  return { schema: "omi.polish.matrix-manifest/v1", capture_class: "native_fixture", source_tier: "native_shell", coordinate_count: coordinates.length, source_shas: { core: coreSha, platform: platformSha }, coordinates };
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function pngCrc(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function fixturePng(width, height) {
  const rows = Buffer.alloc(height * (width * 4 + 1), 0);
  for (let row = 0; row < height; row += 1) {
    const rowStart = row * (width * 4 + 1);
    rows[rowStart] = 0;
    for (let column = 0; column < width; column += 1) rows[rowStart + 1 + column * 4 + 3] = 255;
  }
  rows[1] = 255;
  const chunk = (type, body) => {
    const kind = Buffer.from(type);
    const payload = Buffer.concat([kind, body]);
    const out = Buffer.alloc(12 + body.length);
    out.writeUInt32BE(body.length, 0);
    payload.copy(out, 4);
    out.writeUInt32BE(pngCrc(payload), 8 + body.length);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 6;
  return Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n", "binary"), chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

function uniformFixturePng(width, height) {
  const rows = Buffer.alloc(height * (width * 4 + 1), 0);
  for (let row = 0; row < height; row += 1) {
    const rowStart = row * (width * 4 + 1);
    for (let column = 0; column < width; column += 1) rows[rowStart + 1 + column * 4 + 3] = 255;
  }
  const chunk = (type, body) => {
    const kind = Buffer.from(type);
    const payload = Buffer.concat([kind, body]);
    const out = Buffer.alloc(12 + body.length);
    out.writeUInt32BE(body.length, 0); payload.copy(out, 4); out.writeUInt32BE(pngCrc(payload), 8 + body.length);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 6;
  return Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n", "binary"), chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

function jitterFixturePng(rgb) {
  const rows = Buffer.from([0, ...rgb, 255, 255, 255, 255, 255]);
  const chunk = (type, body) => {
    const kind = Buffer.from(type);
    const payload = Buffer.concat([kind, body]);
    const out = Buffer.alloc(12 + body.length);
    out.writeUInt32BE(body.length, 0); payload.copy(out, 4); out.writeUInt32BE(pngCrc(payload), 8 + body.length);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(2, 0); header.writeUInt32BE(1, 4); header[8] = 8; header[9] = 6;
  return Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n", "binary"), chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

function grayscaleEdgeFixturePng(sample) {
  const width = 7;
  const height = 7;
  const rows = Buffer.alloc(height * (width * 4 + 1));
  for (let row = 0; row < height; row += 1) {
    const rowStart = row * (width * 4 + 1);
    for (let column = 0; column < width; column += 1) {
      const value = column >= 4 ? 224 : 32;
      const offset = rowStart + 1 + column * 4;
      rows[offset] = value;
      rows[offset + 1] = value;
      rows[offset + 2] = value;
      rows[offset + 3] = 255;
    }
  }
  for (const row of [2, 4]) {
    const anchorOffset = row * (width * 4 + 1) + 1 + 3 * 4;
    rows[anchorOffset] = 160;
    rows[anchorOffset + 1] = 160;
    rows[anchorOffset + 2] = 160;
  }
  const sampleOffset = 3 * (width * 4 + 1) + 1 + 3 * 4;
  rows[sampleOffset] = sample;
  rows[sampleOffset + 1] = sample;
  rows[sampleOffset + 2] = sample;
  const chunk = (type, body) => {
    const kind = Buffer.from(type);
    const payload = Buffer.concat([kind, body]);
    const out = Buffer.alloc(12 + body.length);
    out.writeUInt32BE(body.length, 0); payload.copy(out, 4); out.writeUInt32BE(pngCrc(payload), 8 + body.length);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 6;
  return Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n", "binary"), chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

function inputEntriesForFake(manifestPath, appPath) {
  const files = [...new Set([manifestPath, producer, ...walk(appPath)])];
  const entries = files.map((file) => ({ key: `core:${path.relative(root, file)}`, sha256: sha256(readFileSync(file)), size: statSync(file).size, mode: statSync(file).mode & 0o777 })).sort((left, right) => left.key < right.key ? -1 : left.key > right.key ? 1 : 0);
  const tree = sha256(canonical(entries));
  return { id: `input-v1-${tree}`, entries, tree_sha256: tree };
}

function walk(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? walk(file) : [file];
  });
}

test("batch dry-run validates exact coordinate schema and emits one-build plan", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-fixture-batch-"));
  const matrix = path.join(root, ".build", `native-fixture-batch-matrix-${process.pid}.json`);
  try {
    mkdirSync(path.dirname(matrix), { recursive: true });
    const outRoot = path.join(root, ".build", `native-fixture-batch-test-${process.pid}`);
    mkdirSync(path.dirname(outRoot), { recursive: true });
    writeFileSync(matrix, JSON.stringify(manifest([coordinate("macos", "batch-mac"), coordinate("ios", "batch-ios")])));
    const run = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--dry-run"], { encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    const plan = JSON.parse(run.stdout);
    assert.equal(plan.coordinate_count, 2);
    assert.deepEqual(plan.build_once, ["macos", "ios"]);
    assert.equal(plan.authority.bridge, "disabled");
    assert.equal(plan.authority.credentials, false);
    assert.equal(plan.authority.production_api, false);
    assert.match(plan.batch_id_preview, /^batch-v1-[0-9a-f]{64}$/);
    assert.match(plan.command, /capture-native-fixture-batch\.mjs/);
    assert.equal((plan.command.match(/--limit/g) || []).length, 1);
    assert.match(plan.input_set_id, /^input-v1-[0-9a-f]{64}$/);
    assert.equal(plan.coordinates[0].viewport.width, 960);
    assert.equal(plan.coordinates[1].viewport.width, 402);
  } finally {
    rmSync(path.join(root, ".build", `native-fixture-batch-test-${process.pid}`), { recursive: true, force: true });
    rmSync(matrix, { force: true });
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("batch rejects AX/keyboard rows, stale source, and unbound devices before launch", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-fixture-batch-red-"));
  const redRoots = [];
  try {
    const stale = manifest([coordinate("macos", "stale", { source_shas: { core: "2".repeat(40), platform: platformSha } })]);
    stale.source_shas.core = "2".repeat(40);
    // red-proof: changing the batch kind gate to accept ax_snapshot would let
    // an unimplemented semantic capture be reported as a PNG.
    const cases = [
      ["unsupported kind", manifest([coordinate("macos", "bad-kind", { kind: "ax_snapshot" })]), /only screenshot/],
      ["stale source", stale, /does not match current core HEAD/],
      ["missing device", manifest([coordinate("macos", "no-device", { device: undefined })]), /device binding is required/],
      ["extra source", manifest([coordinate("macos", "extra-source", { source_shas: { core: coreSha, platform: platformSha, extra: coreSha } })]), /only full core\/platform/],
    ];
    for (const [name, value, expected] of cases) {
      const matrix = path.join(root, ".build", `native-fixture-batch-red-matrix-${process.pid}-${name.replaceAll(" ", "-")}.json`);
      mkdirSync(path.dirname(matrix), { recursive: true });
      writeFileSync(matrix, JSON.stringify(value));
      const outRoot = path.join(root, ".build", `native-fixture-batch-red-${process.pid}-${name.replaceAll(" ", "-")}`);
      redRoots.push(outRoot);
      mkdirSync(path.dirname(outRoot), { recursive: true });
      const run = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--dry-run"], { encoding: "utf8" });
      assert.notEqual(run.status, 0, name);
      assert.match(run.stderr, expected, name);
      rmSync(matrix, { force: true });
    }
  } finally {
    for (const redRoot of redRoots) rmSync(redRoot, { recursive: true, force: true });
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("batch source has bounded, fixture-only environment and atomic receipt language", () => {
  // red-proof: removing status-bar override/clear or the consecutive hash
  // comparison would make simulator time and animation bytes silently drift.
  const source = readFileSync(producer, "utf8");
  const appDelegate = readFileSync(path.join(root, "shells/ios/app/ios/Runner/AppDelegate.swift"), "utf8");
  const sceneDelegate = readFileSync(path.join(root, "shells/ios/app/ios/Runner/SceneDelegate.swift"), "utf8");
  const captureController = readFileSync(path.join(root, "shells/ios/app/ios/Runner/CaptureFlutterViewController.swift"), "utf8");
  const mainStoryboard = readFileSync(path.join(root, "shells/ios/app/ios/Runner/Base.lproj/Main.storyboard"), "utf8");
  const iosProject = readFileSync(path.join(root, "shells/ios/app/ios/Runner.xcodeproj/project.pbxproj"), "utf8");
  const dartHost = readFileSync(path.join(root, "shells/ios/app/lib/main.dart"), "utf8");
  assert.match(source, /const maxCoordinates = 1236/);
  assert.match(source, /OMI_SURFACE_PORT = "5290"/);
  assert.match(source, /credentials: false/);
  assert.match(source, /production_api: false/);
  assert.match(source, /writeAtomic\(resultPath/);
  assert.match(source, /buildMac\(manifest/);
  assert.match(source, /buildIos\(manifest/);
  assert.match(source, /status_bar.*override/);
  assert.match(source, /status_bar.*clear/);
  assert.match(source, /let launched = false/);
  assert.match(source, /finally \{\n    if \(launched\)/);
  assert.match(source, /batch-v1-/);
  assert.match(source, /omi\.polish\.screenshot\/v1/);
  assert.match(source, /batch_members/);
  assert.match(source, /artifact_before_hashes/);
  assert.match(source, /omi\.polish\.native-fixture-batch-result\/v1/);
  assert.match(source, /NATIVE_FIXTURE_BATCH_COMPLETE members=/);
  assert.match(source, /assemble-receipt/);
  assert.match(source, /replay_proof/);
  assert.match(source, /maxBatchCoordinates = 32/);
  assert.match(source, /prepared-input-set/);
  assert.match(source, /preparedDescriptor\.input_set/);
  assert.match(source, /prepared app contains unsupported symlink/);
  assert.match(source, /artifact\?\.stamp/);
  assert.match(source, /ensureCoreFile\(String\(item\.stamp/);
  assert.match(source, /prepared iOS bundle id is not the capture shell/);
  assert.match(source, /screenConfig.*geometry/);
  assert.match(source, /viewport\.width \* viewport\.scale/);
  assert.match(source, /flutter, \["config", `--build-dir=/);
  assert.match(source, /ios\/Flutter\/ephemeral/);
  assert.match(source, /rmSync\(ephemeral, \{ recursive: true, force: true \}\)/);
  assert.match(source, /found nothing to terminate/);
  assert.match(source, /--omi-capture-run-id=/);
  assert.match(source, /--omi-capture-nonce=/);
  assert.match(source, /omi-native-capture-ready\.json/);
  assert.match(source, /simctl", "spawn"/);
  assert.match(source, /marker\.nonce === nonce/);
  assert.match(source, /marker\.polish_state === coordinate\.state/);
  assert.match(source, /fixturePolicy\[coordinate\.domain\]/);
  assert.match(source, /settle simulator compositor/);
  assert.match(source, /warmup\.png/);
  assert.match(appDelegate, /name: "omi\/capture-launch"/);
  assert.match(appDelegate, /capture-ready-invalid/);
  assert.match(appDelegate, /capture-ready-write-failed/);
  assert.match(appDelegate, /omi-native-capture-ready\.json/);
  assert.match(dartHost, /_captureOnly && msg\.message\.contains\('OMI_PRODUCTION_READY'\)/);
  assert.match(dartHost, /_beginCaptureReadiness\(\)/);
  assert.match(dartHost, /dataset\.polishState/);
  assert.match(dartHost, /page-finished callback precedes React's typed fixture root/);
  assert.match(appDelegate, /NATIVE_CAPTURE_READY run_id=%@ route=%@ fixture=%@ state=%@/);
  assert.match(sceneDelegate, /--omi-capture-query=/);
  assert.match(sceneDelegate, /setNeedsUpdateOfHomeIndicatorAutoHidden/);
  assert.match(captureController, /prefersHomeIndicatorAutoHidden/);
  assert.match(captureController, /--omi-capture-query=/);
  assert.match(mainStoryboard, /customClass="CaptureFlutterViewController"/);
  assert.match(iosProject, /CaptureFlutterViewController\.swift in Sources/);
  assert.match(source, /simctl.*ui.*appearance/);
  assert.match(source, /\/usr\/bin\/lsappinfo/);
  assert.match(source, /assertNoForbiddenForeground\(forbiddenForeground, `\$\{coordinate\.run_id\}: preflight`\)/);
  assert.match(source, /assertNoForbiddenForeground\(forbiddenForeground, `\$\{coordinate\.run_id\}: simulator launch`\)/);
  assert.match(source, /assertNoForbiddenForeground\(forbiddenForeground, `\$\{coordinate\.run_id\}: simulator screenshot`\)/);
  assert.match(source, /assertNoForbiddenForeground\(forbiddenForeground, `\$\{coordinate\.run_id\}: cleanup`\)/);
  assert.match(source, /assertNoForbiddenForeground\(forbiddenForeground, `\$\{coordinate\.run_id\}: iOS fixture preparation`\)/);
  assert.match(source, /sampled-20ms-forbidden-fixture-foreground-detection-no-activation-request/);
  assert.match(source, /startForbiddenForegroundMonitor/);
  assert.match(source, /native batch final restoration/);
  assert.match(source, /artifacts\.macos\.bundleId/);
  assert.doesNotMatch(source, /open(?:Sync)?\([^\n]*Simulator/);
  assert.doesNotMatch(source, /osascript/);
  assert.match(source, /elapsedSeconds/);
  assert.match(source, /canonicalizeScreenshot/);
  assert.match(source, /value < 16/);
  assert.match(source, /distance > 6/);
  assert.match(source, /tablet status bar may draw a spinner/);
  assert.match(source, /Wide iPad simulators retain a centered system home-indicator/);
  assert.match(source, /diagnostics.*replay-mismatch/);
  assert.match(source, /first\.raw\.png/);
  assert.match(source, /repeat\.raw\.png/);
  assert.match(source, /validAccessibilities = new Set\(\["none"\]\)/);
  assert.doesNotMatch(source, /const env = \{ \.\.\.process\.env \}/);
  assert.doesNotMatch(source, /OMI_API_TOKEN/);
});

test("iOS foreground guard allows user app switching but rejects fixture foreground", () => {
  const front = { status: 0, signal: null, stdout: "ASN:0x0-0x1001:\n" };
  const userInfo = { status: 0, signal: null, stdout: '\"CFBundleIdentifier\"=\"com.openai.codex\"\n' };
  const otherInfo = { status: 0, signal: null, stdout: '\"CFBundleIdentifier\"=\"com.anthropic.claudefordesktop\"\n' };
  const fixtureInfo = { status: 0, signal: null, stdout: '\"CFBundleIdentifier\"=\"com.apple.iphonesimulator\"\n' };
  assert.doesNotThrow(() => assertMacForegroundProbeTransitionForTest(front, userInfo, { ...front, stdout: "ASN:0x0-0x2002:\n" }, otherInfo));
  assert.throws(() => assertMacForegroundProbeTransitionForTest(front, userInfo, front, fixtureInfo), /forbidden fixture application/);
  assert.throws(
    () => assertMacForegroundProbeTransitionForTest(front, userInfo, { ...front, status: 1, stdout: "" }, otherInfo),
    /unable to bind the current macOS foreground application/,
  );
  assert.throws(
    () => assertMacForegroundProbeTransitionForTest({ ...front, error: { code: "ETIMEDOUT" } }, userInfo, front, otherInfo),
    /foreground-app probe timed out/,
  );
});

test("iOS continuous foreground monitor observes the real host without activating it", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-focus-monitor-"));
  try {
    const front = spawnSync("/usr/bin/lsappinfo", ["front"], { encoding: "utf8" });
    assert.equal(front.status, 0);
    assert.match(front.stdout.trim(), /^ASN:0x[0-9a-f]+-0x[0-9a-f]+:$/i);
    const ready = path.join(scratch, "ready.json");
    const stop = path.join(scratch, "stop");
    const violation = path.join(scratch, "violation.json");
    const done = path.join(scratch, "done.json");
    writeFileSync(stop, "stop\n");
    const monitor = spawnSync(process.execPath, [producer, "--foreground-monitor", JSON.stringify(["com.example.never-front"]), ready, stop, violation, done], { encoding: "utf8", timeout: 5_000 });
    assert.equal(monitor.status, 0, monitor.stderr);
    assert.equal(existsSync(violation), false);
    assert.equal(existsSync(done), true);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("iOS foreground custody fails closed when its monitor dies after readiness", () => {
  assert.doesNotThrow(() => assertForegroundMonitorCompletionForTest(true));
  assert.throws(() => assertForegroundMonitorCompletionForTest(false), /foreground monitor stopped without a terminal receipt/);
  assert.throws(() => assertForegroundMonitorCompletionForTest(true, { reason: "changed" }), /focus custody failed: changed/);
  const source = readFileSync(producer, "utf8");
  assert.match(source, /finally \{\s*foregroundMonitor = null;\s*for \(const artifact of Object\.values\(artifacts\)\) cleanupEnvironment\(artifact\.env\);/);
});

test("screenshot canonicalization removes low-bit compositor jitter but preserves visible changes", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-fixture-pixels-"));
  try {
    const first = path.join(scratch, "first.png");
    const second = path.join(scratch, "second.png");
    const changed = path.join(scratch, "changed.png");
    writeFileSync(first, jitterFixturePng([3, 10, 13]));
    writeFileSync(second, jitterFixturePng([4, 9, 12]));
    writeFileSync(changed, jitterFixturePng([35, 10, 13]));
    canonicalizeScreenshotForTest(first);
    canonicalizeScreenshotForTest(second);
    canonicalizeScreenshotForTest(changed);
    assert.deepEqual(readFileSync(first), readFileSync(second));
    assert.notDeepEqual(readFileSync(first), readFileSync(changed));
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("screenshot canonicalization collapses bounded grayscale glyph-edge variants", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-fixture-edge-pixels-"));
  try {
    const first = path.join(scratch, "first.png");
    const second = path.join(scratch, "second.png");
    const changed = path.join(scratch, "changed.png");
    writeFileSync(first, grayscaleEdgeFixturePng(157));
    writeFileSync(second, grayscaleEdgeFixturePng(163));
    writeFileSync(changed, grayscaleEdgeFixturePng(96));
    canonicalizeScreenshotForTest(first);
    canonicalizeScreenshotForTest(second);
    canonicalizeScreenshotForTest(changed);
    assert.deepEqual(readFileSync(first), readFileSync(second));
    assert.notDeepEqual(readFileSync(first), readFileSync(changed));
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("batch boundaries require prepared inputs and reject oversized/semantic ranges", () => {
  const scratch = mkdtempSync(path.join(tmpdir(), "omi-native-fixture-boundary-"));
  try {
    const many = Array.from({ length: 33 }, (_, index) => coordinate("macos", `row-${index}`));
    const matrix = path.join(root, ".build", `native-fixture-boundary-${process.pid}.json`);
    const outRoot = path.join(root, ".build", `native-fixture-boundary-out-${process.pid}`);
    mkdirSync(path.dirname(matrix), { recursive: true });
    writeFileSync(matrix, JSON.stringify(manifest(many)));
    const oversized = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--limit", "33"], { encoding: "utf8" });
    assert.notEqual(oversized.status, 0);
    assert.match(oversized.stderr, /--limit must be 1\.\.32/);
    const needsPrepared = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--limit", "1"], { encoding: "utf8" });
    assert.notEqual(needsPrepared.status, 0);
    assert.match(needsPrepared.stderr, /requires --prepared-input-set/);
    const keyboard = manifest([coordinate("macos", "keyboard", { accessibility: "keyboard" })]);
    const keyboardMatrix = path.join(root, ".build", `native-fixture-keyboard-${process.pid}.json`);
    writeFileSync(keyboardMatrix, JSON.stringify(keyboard));
    const keyboardRun = spawnSync(process.execPath, [producer, "--manifest", keyboardMatrix, "--out-root", outRoot, "--dry-run"], { encoding: "utf8" });
    assert.notEqual(keyboardRun.status, 0);
    assert.match(keyboardRun.stderr, /accessibility/);
    rmSync(keyboardMatrix, { force: true });
    rmSync(matrix, { force: true });
    rmSync(outRoot, { recursive: true, force: true });
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("assemble-receipt binds result manifest separately from replay artifacts", () => {
  const outRoot = path.join(root, ".build", `native-fixture-assemble-${process.pid}`);
  const matrix = path.join(root, ".build", `native-fixture-assemble-matrix-${process.pid}.json`);
  const image = path.join(outRoot, "captures/macos/fake.png");
  const sidecar = `${image}.sidecar.json`;
  const resultPath = path.join(outRoot, "batch-result.json");
  try {
    mkdirSync(path.dirname(image), { recursive: true });
    const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64");
    writeFileSync(image, png);
    const coordinate = coordinateForAssembly();
    writeFileSync(sidecar, JSON.stringify({ schema: "omi.polish.screenshot/v1", domain: coordinate.domain, shell: coordinate.shell, state: coordinate.state, theme: coordinate.theme, width: coordinate.width, accessibility: "none", run_id: coordinate.run_id, source_shas: coordinate.source_shas, capture_class: "native_fixture", source_tier: "native_shell", image_root: "core", image_path: `core:${path.relative(root, image)}`, image_sha256: sha256(png) }));
    const value = manifest([coordinate]);
    writeFileSync(matrix, JSON.stringify(value));
    const members = { m0000: { coordinate: ["screenshot", coordinate.domain, coordinate.shell, coordinate.state, coordinate.theme, coordinate.width, "none"], run_id: coordinate.run_id, evidence: { root: "core", path: path.relative(root, image), sha256: sha256(png) }, sidecar: { root: "core", path: path.relative(root, sidecar), sha256: sha256(readFileSync(sidecar)) } } };
    const authority = { fixture: true, bridge: "disabled", credentials: false, production_api: false, focus_policy: { macos: nativeFocusPolicyForTest(), ios: nativeFocusPolicyForTest() }, origins: { macos: "http://127.0.0.1:5290", ios: "omi-ui://local" } };
    const result = { schema: "omi.polish.native-fixture-batch-result/v1", source_shas: value.source_shas, manifest_path: `core:${path.relative(root, matrix)}`, manifest_sha256: sha256(readFileSync(matrix)), command: "node capture-native-fixture-batch.mjs", argv: ["node", "capture-native-fixture-batch.mjs"], input_set: { id: `input-v1-${"a".repeat(64)}`, entries: [], tree_sha256: "a".repeat(64) }, members, timeout_seconds: 300, wait_seconds: 1, stdout_sha256: sha256("NATIVE_FIXTURE_BATCH_COMPLETE members=1\n"), stderr_sha256: sha256(""), authority };
    writeFileSync(resultPath, JSON.stringify(result, null, 2));
    const forged = { ...result, authority: { fixture: true } };
    writeFileSync(resultPath, JSON.stringify(forged, null, 2));
    const rejected = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--assemble-receipt", "--result-path", resultPath, "--started-at", "2026-08-11T12:00:00.000Z", "--finished-at", "2026-08-11T12:00:01.000Z"], { encoding: "utf8" });
    assert.notEqual(rejected.status, 0);
    assert.match(rejected.stderr, /authority\/focus policy is invalid/);
    writeFileSync(resultPath, JSON.stringify(result, null, 2));
    const run = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--assemble-receipt", "--result-path", resultPath, "--started-at", "2026-08-11T12:00:00.000Z", "--finished-at", "2026-08-11T12:00:01.000Z"], { encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    const receiptPath = run.stdout.match(/file=(.+\.receipt\.json)/)?.[1];
    assert.ok(receiptPath);
    const receipt = JSON.parse(readFileSync(path.join(root, receiptPath), "utf8"));
    assert.match(receipt.batch_id, /^batch-v1-[0-9a-f]{64}$/);
    assert.ok(receipt.command_receipt.artifact_hashes[`core:${path.relative(root, resultPath)}`]);
    assert.equal(receipt.coverage.length, 1);
  } finally {
    rmSync(outRoot, { recursive: true, force: true });
    rmSync(matrix, { force: true });
  }
});

test("one manifest-scoped prepared app can capture a later coordinate deterministically", () => {
  const outRoot = path.join(root, ".build", `native-fixture-fake-capture-${process.pid}`);
  const matrix = path.join(root, ".build", `native-fixture-fake-capture-matrix-${process.pid}.json`);
  try {
    const coordinate = coordinateForAssembly();
    const secondCoordinate = { ...coordinate, run_id: "assembly-fake-dark", theme: "dark", surface_query: coordinate.surface_query.replace("theme=light", "theme=dark") };
    writeFileSync(matrix, JSON.stringify(manifest([coordinate, secondCoordinate])));
    const app = path.join(outRoot, "build/macos/omi-on-polish-batch.app");
    const executable = path.join(app, "Contents/MacOS/omi-on-polish-batch");
    const resources = path.join(app, "Contents/Resources");
    mkdirSync(path.dirname(executable), { recursive: true });
    mkdirSync(resources, { recursive: true });
    writeFileSync(path.join(app, "Contents/Info.plist"), `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>CFBundleIdentifier</key><string>me.omi.capture.test</string></dict></plist>\n`);
    const fakeImage = path.join(resources, "fake.png");
    writeFileSync(fakeImage, uniformFixturePng(960, 671));
    writeFileSync(path.join(resources, "omi-build-stamp.json"), "{\"fixture\":true}\n");
    writeFileSync(executable, "#!/bin/sh\ncp \"$(dirname \"$0\")/../Resources/fake.png\" \"$OMI_SNAPSHOT_PATH\"\n");
    chmodSync(executable, 0o755);
    const preparedPath = path.join(outRoot, "prepared-input-set.json");
    const descriptor = {
      schema: "omi.polish.native-fixture-prepared/v1", source_shas: { core: coreSha, platform: platformSha }, manifest_path: `core:${path.relative(root, matrix)}`, manifest_sha256: sha256(readFileSync(matrix)), shell: "macos", scope: "manifest-shell", coordinate_run_ids: [coordinate.run_id, secondCoordinate.run_id],
      artifacts: { macos: { shell: "macos", app: `core:${path.relative(root, app)}`, build_dir: `core:${path.relative(root, path.join(outRoot, "build/macos"))}`, stamp: `core:${path.relative(root, path.join(app, "Contents/Resources/omi-build-stamp.json"))}`, stamp_sha256: sha256(readFileSync(path.join(app, "Contents/Resources/omi-build-stamp.json"))), bundle_id: "me.omi.capture.test" } },
      authority: { fixture: true, bridge: "disabled", credentials: false, production_api: false, focus_policy: { macos: nativeFocusPolicyForTest(), ios: nativeFocusPolicyForTest() }, origins: { macos: "http://127.0.0.1:5290", ios: "omi-ui://local" } },
    };
    descriptor.input_set = inputEntriesForFake(matrix, app);
    mkdirSync(outRoot, { recursive: true });
    writeFileSync(preparedPath, JSON.stringify(descriptor, null, 2));
    const uniform = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--shell", "macos", "--offset", "1", "--limit", "1", "--prepared-input-set", preparedPath, "--timeout-seconds", "60"], { encoding: "utf8" });
    assert.notEqual(uniform.status, 0);
    assert.match(uniform.stderr, /uniform framebuffer and cannot prove rendered UI/);
    writeFileSync(fakeImage, fixturePng(960, 671));
    descriptor.input_set = inputEntriesForFake(matrix, app);
    writeFileSync(preparedPath, JSON.stringify(descriptor, null, 2));
    const run = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--shell", "macos", "--offset", "1", "--limit", "1", "--prepared-input-set", preparedPath, "--timeout-seconds", "60", "--replay-proof"], { encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    assert.match(run.stdout, /NATIVE_FIXTURE_BATCH_COMPLETE members=1/);
    const result = JSON.parse(readFileSync(path.join(outRoot, "batch-result-macos-1-1.json"), "utf8"));
    assert.equal(result.schema, "omi.polish.native-fixture-batch-result/v1");
    assert.equal(result.batch_id, undefined);
    assert.equal(Object.keys(result.members).length, 1);
    const image = path.join(outRoot, "captures/macos/assembly-fake-dark.png");
    assert.equal(readFileSync(image).length, fixturePng(960, 671).length);
    const firstRange = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--shell", "macos", "--offset", "0", "--limit", "1", "--prepared-input-set", preparedPath, "--timeout-seconds", "60"], { encoding: "utf8" });
    assert.equal(firstRange.status, 0, firstRange.stderr);
    assert.equal(readFileSync(path.join(outRoot, "batch-result-macos-0-1.json"), "utf8").length > 0, true);
    assert.equal(readFileSync(path.join(outRoot, "batch-result-macos-1-1.json"), "utf8").length > 0, true);
    descriptor.coordinate_run_ids = [secondCoordinate.run_id];
    writeFileSync(preparedPath, JSON.stringify(descriptor, null, 2));
    const narrowed = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--shell", "macos", "--offset", "1", "--limit", "1", "--prepared-input-set", preparedPath, "--timeout-seconds", "60"], { encoding: "utf8" });
    assert.notEqual(narrowed.status, 0);
    assert.match(narrowed.stderr, /coordinate scope is stale/);
  } finally {
    rmSync(outRoot, { recursive: true, force: true });
    rmSync(matrix, { force: true });
  }
});

function coordinateForAssembly() {
  return coordinate("macos", "assembly-fake", { width: "regular" });
}
