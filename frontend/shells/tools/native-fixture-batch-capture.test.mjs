import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { deflateSync } from "node:zlib";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const producer = path.join(root, "shells/tools/capture-native-fixture-batch.mjs");
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
  for (let row = 0; row < height; row += 1) rows[row * (width * 4 + 1)] = 0;
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

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

function inputEntriesForFake(manifestPath, appPath) {
  const files = [...new Set([manifestPath, producer, ...walk(appPath)])];
  const entries = files.map((file) => ({ key: `core:${path.relative(root, file)}`, sha256: sha256(readFileSync(file)), size: statSync(file).size, mode: statSync(file).mode & 0o777 })).sort((left, right) => left.key.localeCompare(right.key));
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
  assert.match(source, /found nothing to terminate/);
  assert.match(source, /--omi-capture-run-id=/);
  assert.match(source, /--omi-capture-nonce=/);
  assert.match(source, /omi-native-capture-ready\.json/);
  assert.match(source, /simctl", "spawn"/);
  assert.match(source, /marker\.nonce === nonce/);
  assert.match(appDelegate, /name: "omi\/capture-launch"/);
  assert.match(appDelegate, /capture-ready-invalid/);
  assert.match(appDelegate, /capture-ready-write-failed/);
  assert.match(appDelegate, /omi-native-capture-ready\.json/);
  assert.match(appDelegate, /NATIVE_CAPTURE_READY run_id=%@ route=%@ fixture=%@ state=%@/);
  assert.match(source, /simctl.*ui.*appearance/);
  assert.match(source, /elapsedSeconds/);
  assert.match(source, /validAccessibilities = new Set\(\["none"\]\)/);
  assert.doesNotMatch(source, /const env = \{ \.\.\.process\.env \}/);
  assert.doesNotMatch(source, /OMI_API_TOKEN/);
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
    const result = { schema: "omi.polish.native-fixture-batch-result/v1", source_shas: value.source_shas, manifest_path: `core:${path.relative(root, matrix)}`, manifest_sha256: sha256(readFileSync(matrix)), command: "node capture-native-fixture-batch.mjs", argv: ["node", "capture-native-fixture-batch.mjs"], input_set: { id: `input-v1-${"a".repeat(64)}`, entries: [], tree_sha256: "a".repeat(64) }, members, timeout_seconds: 300, wait_seconds: 1, stdout_sha256: sha256("NATIVE_FIXTURE_BATCH_COMPLETE members=1\n"), stderr_sha256: sha256(""), authority: { fixture: true } };
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

test("prepared one-coordinate capture recreates PNG, sidecar, and result deterministically", () => {
  const outRoot = path.join(root, ".build", `native-fixture-fake-capture-${process.pid}`);
  const matrix = path.join(root, ".build", `native-fixture-fake-capture-matrix-${process.pid}.json`);
  try {
    const coordinate = coordinateForAssembly();
    writeFileSync(matrix, JSON.stringify(manifest([coordinate])));
    const app = path.join(outRoot, "build/macos/omi-on-polish-batch.app");
    const executable = path.join(app, "Contents/MacOS/omi-on-polish-batch");
    const resources = path.join(app, "Contents/Resources");
    mkdirSync(path.dirname(executable), { recursive: true });
    mkdirSync(resources, { recursive: true });
    writeFileSync(path.join(resources, "fake.png"), fixturePng(960, 671));
    writeFileSync(path.join(resources, "omi-build-stamp.json"), "{\"fixture\":true}\n");
    writeFileSync(executable, "#!/bin/sh\ncp \"$(dirname \"$0\")/../Resources/fake.png\" \"$OMI_SNAPSHOT_PATH\"\n");
    chmodSync(executable, 0o755);
    const preparedPath = path.join(outRoot, "prepared-input-set.json");
    const descriptor = {
      schema: "omi.polish.native-fixture-prepared/v1", source_shas: { core: coreSha, platform: platformSha }, manifest_path: `core:${path.relative(root, matrix)}`, manifest_sha256: sha256(readFileSync(matrix)), shell: "macos", offset: 0, limit: 1, coordinate_run_ids: [coordinate.run_id],
      artifacts: { macos: { shell: "macos", app: `core:${path.relative(root, app)}`, build_dir: `core:${path.relative(root, path.join(outRoot, "build/macos"))}`, stamp: `core:${path.relative(root, path.join(app, "Contents/Resources/omi-build-stamp.json"))}`, stamp_sha256: sha256(readFileSync(path.join(app, "Contents/Resources/omi-build-stamp.json"))), bundle_id: null } },
      authority: { fixture: true, bridge: "disabled", credentials: false, production_api: false, origins: { macos: "http://127.0.0.1:5290", ios: "omi-ui://local" } },
    };
    descriptor.input_set = inputEntriesForFake(matrix, app);
    mkdirSync(outRoot, { recursive: true });
    writeFileSync(preparedPath, JSON.stringify(descriptor, null, 2));
    const run = spawnSync(process.execPath, [producer, "--manifest", matrix, "--out-root", outRoot, "--shell", "macos", "--offset", "0", "--limit", "1", "--prepared-input-set", preparedPath, "--timeout-seconds", "60", "--replay-proof"], { encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    assert.match(run.stdout, /NATIVE_FIXTURE_BATCH_COMPLETE members=1/);
    const result = JSON.parse(readFileSync(path.join(outRoot, "batch-result.json"), "utf8"));
    assert.equal(result.schema, "omi.polish.native-fixture-batch-result/v1");
    assert.equal(result.batch_id, undefined);
    assert.equal(Object.keys(result.members).length, 1);
    const image = path.join(outRoot, "captures/macos/assembly-fake.png");
    assert.equal(readFileSync(image).length, fixturePng(960, 671).length);
  } finally {
    rmSync(outRoot, { recursive: true, force: true });
    rmSync(matrix, { force: true });
  }
});

function coordinateForAssembly() {
  return coordinate("macos", "assembly-fake", { width: "regular" });
}
