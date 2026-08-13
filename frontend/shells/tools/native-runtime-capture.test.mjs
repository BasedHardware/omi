import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  gateReplay,
  macRuntimeAppName,
  parseMacProbe,
  runtimeProbeScript,
  runtimeFixtureName,
  validateHostMarker,
  validateManifest,
} from "./capture-native-runtime.mjs";

const root = path.resolve(import.meta.dirname, "../..");
const producer = path.join(root, "shells/tools/capture-native-runtime.mjs");
const coreSha = spawnSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).stdout.trim();
const platformSha = "1".repeat(40);
mkdirSync(path.join(root, ".build"), { recursive: true });

function manifest(overrides = {}) {
  return {
    schema: "omi.polish.matrix-coordinate/v1", kind: "runtime_trace", domain: "chat", shell: "macos",
    state: "ready", theme: "dark", width: "regular", accessibility: "none", run_id: "runtime-test-1",
    capture_class: "native_fixture", source_tier: "native_shell", source_shas: { core: coreSha, platform: platformSha },
    surface_query: "polish=1&qa=chat&state=ready&platform=desktop&theme=dark&width=regular&accessibility=none&locale=en-US",
    device: { udid: "macos-local", model: "Mac17,7", orientation: "landscape" },
    viewport: { width: 960, height: 671, scale: 2 }, ...overrides,
  };
}

function marker(m, events = [{ type: "lifecycle", name: "state", value: m.state, passed: true }]) {
  return { schema: "omi.native-runtime-marker/v1", domain: m.domain, theme: m.theme, accessibility: m.accessibility, events };
}

function writePreparation(file, m, artifactPath, artifactBytes) {
  const guard = path.join(root, "shells/tools/macos-foreground-guard.mjs");
  const outputDir = path.dirname(artifactPath);
  const guarded = m.shell === "macos"
    ? ["/bin/bash", path.join(root, "shells/macos/scripts/dev-run-macos.sh"), "--fixture", runtimeFixtureName(m.domain), "--state", m.state, "--theme", m.theme, "--accessibility", m.accessibility, "--run-id", m.run_id, "--capture-out", path.join(outputDir, "probe.png"), "--viewport-width", String(m.viewport.width), "--viewport-height", String(m.viewport.height)]
    : ["xcodebuild", "test", "-project", path.join(root, "shells/ios/app/ios/Runner.xcodeproj"), "-scheme", "Runner", "-destination", `platform=iOS Simulator,id=${m.device.udid}`, "-only-testing", "RunnerUITests/NativeRuntimeEvidenceUITests/testNativeRuntimeEvidence", "-parallel-testing-enabled", "NO", "-derivedDataPath", path.join(outputDir, "DerivedData"), "-resultBundlePath", path.join(outputDir, "Runner.xcresult"), "CODE_SIGNING_ALLOWED=NO", "FLUTTER_ROOT=/opt/flutter"];
  writeFileSync(file, `${JSON.stringify({
    schema: "omi.polish.runtime-preparation/v1",
    domain: m.domain, shell: m.shell, state: m.state, theme: m.theme, width: m.width, accessibility: m.accessibility,
    run_id: m.run_id, source_shas: m.source_shas, capture_class: m.capture_class, source_tier: m.source_tier,
    command: {
      argv: [process.execPath, guard, "--result", path.join(outputDir, "foreground-guard.json"), "--stdout", path.join(outputDir, m.shell === "macos" ? "foreground-guard.stdout.log" : "xcodebuild.stdout"), "--stderr", path.join(outputDir, m.shell === "macos" ? "foreground-guard.stderr.log" : "xcodebuild.stderr"), "--timeout", "300", "--forbid-bundle-ids", "com.apple.iphonesimulator,me.omi.proto.omiWebviewProto,me.omi.shell.core-tasks.prototype", "--", ...guarded],
      cwd: ".", cwd_root: "core", exit_code: 0, timeout_seconds: 310,
      stdout_sha256: "0".repeat(64), stderr_sha256: "0".repeat(64),
    },
    foreground_custody: {
      schema: "omi.macos-foreground-guard/v1", status: 0, signal: null, error: null, monitor_error: null,
      target_interval_milliseconds: 20, probe_timeout_milliseconds: 250, sample_count: 2, max_sample_gap_milliseconds: 20,
      forbidden_bundle_ids: ["com.apple.iphonesimulator", "me.omi.proto.omiWebviewProto", "me.omi.shell.core-tasks.prototype"],
      policy: "sampled-macos-forbidden-fixture-foreground-detection-20ms-target-250ms-probe-timeout-no-activation-request",
    },
    artifact: { root: "core", path: path.relative(root, artifactPath), sha256: createHash("sha256").update(artifactBytes).digest("hex") },
  })}\n`);
}

test("runtime manifest is immutable and cannot be relabelled as browser or unsupported lifecycle", () => {
  assert.throws(() => validateManifest(manifest({ capture_class: "core_browser_preview" })), /native_fixture/);
  assert.throws(() => validateManifest(manifest({ width: "compact" })), /width=regular/);
  assert.throws(() => validateManifest(manifest({ domain: "settings", state: "cancelled" })), /not applicable/);
  assert.throws(() => validateManifest(manifest({ accessibility: "voiceover" })), /unsupported coordinate/);
  assert.throws(() => validateManifest(manifest({ accessibility: "reduced_motion", state: "busy" })), /state=ready/);
  assert.throws(() => validateManifest(manifest({ surface_query: "polish=1&qa=chat&state=busy" })), /surface_query/);
  assert.throws(() => validateManifest(manifest({ device: { udid: "other", model: "Mac17,7", orientation: "landscape" } })), /device/);
});

test("Memories runtime binds the platform fixture alias to the normalized domain", () => {
  const memories = manifest({
    domain: "memories",
    state: "busy",
    surface_query: "polish=1&qa=memories-platform&state=busy&platform=desktop&theme=dark&width=regular&accessibility=none&locale=en-US",
  });
  assert.doesNotThrow(() => validateManifest(memories));
  assert.equal(runtimeFixtureName(memories.domain), "memories-platform");
  assert.equal(runtimeFixtureName("chat"), "chat");
  const probe = runtimeProbeScript(memories);
  assert.match(probe, /expectedQa = "memories-platform"/);
  assert.match(probe, /domain:expectedDomain/);
  assert.throws(() => validateManifest({ ...memories, surface_query: memories.surface_query.replace("memories-platform", "memories") }), /surface_query/);
});

test("native shell custody is explicit and browser shortcuts are absent", () => {
  const source = readFileSync(producer, "utf8");
  const iosHook = readFileSync(path.join(root, "shells/ios/app/ios/Runner/OmiUiWebView.swift"), "utf8");
  const appDelegate = readFileSync(path.join(root, "shells/ios/app/ios/Runner/AppDelegate.swift"), "utf8");
  const macHost = readFileSync(path.join(root, "shells/macos/shell/Sources/OmiShell/main.swift"), "utf8");
  assert.match(source, /dev-run-macos\.sh/);
  assert.match(source, /OMI_PROBE_JS/);
  assert.match(source, /OMI_PROBE_PENDING_VALUE/);
  assert.match(source, /OMI_PROBE_MAX_ATTEMPTS/);
  assert.match(source, /OMI_ACCEPTANCE_WAIT_SECONDS = "30"/);
  assert.match(macHost, /attempt < maxAttempts && \(error != nil \|\| pending\)/);
  assert.match(source, /xcodebuild/);
  assert.match(source, /macos-foreground-guard\.mjs/);
  assert.match(source, /macOS runtime foreground guard produced no terminal receipt/);
  assert.match(source, /validateForegroundCustody\(preparation\.foreground_custody\)/);
  assert.match(source, /monitor_error !== null/);
  assert.match(source, /xcresulttool/);
  assert.match(source, /OMI_NATIVE_IOS_RUNTIME_JSON\(\?:_\\d\+_\[0-9A-F-\]\{36\}\)\?/);
  assert.match(source, /allowedEnvironment/);
  assert.match(source, /mkdirSync\(scratch, \{ recursive: true \}\)/);
  assert.match(source, /--emit-gate-records false/);
  assert.doesNotMatch(source, /core_browser_preview/);
  assert.match(iosHook, /OMI_POLISH_RUNTIME_PROBE/);
  assert.match(appDelegate, /OmiRuntimeProbeHandler\.installIfRequested/);
  assert.match(iosHook, /omiRuntimeProbe/);
  assert.match(iosHook, /omi\.native-runtime-marker\/v1/);
  assert.match(iosHook, /computed_style/);
  assert.match(iosHook, /attempts < 80/);
  assert.match(iosHook, /polishState !== wantedState/);
  assert.match(iosHook, /requestedQa === "memories-platform" \? "memories" : requestedQa/);
  assert.match(source, /document\.documentElement\.dataset\.polishState/);
  assert.doesNotMatch(source, /value:root\.dataset\.surfaceState/);
  assert.doesNotMatch(iosHook, /OMI_API_TOKEN/);
});

test("macOS scratch app name binds arbitrary matrix run IDs without weakening launcher grammar", () => {
  const runId = "mx-v1-runtime_trace-chat-macos-busy-dark-regular-none";
  const name = macRuntimeAppName(runId);
  assert.match(name, /^omi-on-[A-Za-z0-9][A-Za-z0-9.-]*$/);
  assert.equal(name, macRuntimeAppName(runId));
  assert.notEqual(name, macRuntimeAppName(`${runId}-other`));
  assert.doesNotMatch(name, /runtime_trace|chat|busy/);
  assert.throws(() => macRuntimeAppName("bad run id"), /run_id/);
});

test("macOS probe parser requires one real successful WK result", () => {
  const m = manifest();
  const good = `PROBE_JS: ${JSON.stringify(marker(m))} error: none`;
  assert.doesNotThrow(() => parseMacProbe(good, m));
  assert.throws(() => parseMacProbe(`${good}\n${good}`, m), /exactly one/);
  assert.throws(() => parseMacProbe(`PROBE_JS: ${JSON.stringify(marker(m))} error: Error`, m), /exactly one/);
  assert.throws(() => parseMacProbe(`PROBE_JS: {"schema":"omi.native-runtime-marker/v1","domain":"chat","theme":"dark","accessibility":"none","events":[] } error: none`, m), /events/);
});

test("live capture refuses to claim a shell when platform provenance is absent", () => {
  const scratch = mkdtempSync(path.join(root, ".build", "runtime-provenance-test-"));
  try {
    const file = path.join(scratch, "coordinate.json");
    writeFileSync(file, `${JSON.stringify(manifest())}\n`);
    const run = spawnSync(process.execPath, [producer, "--manifest", file, "--output-dir", scratch], { cwd: root, encoding: "utf8" });
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /platform SHA/);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("runtime host marker requires typed native events and rejects hostile values", () => {
  const m = manifest();
  assert.deepEqual(validateHostMarker(marker(m), m).events[0], { type: "lifecycle", name: "state", value: "ready", passed: true });
  assert.throws(() => validateHostMarker(marker(m, [{ type: "lifecycle", name: "state", value: "ready", passed: true, secret: "token" }]), m), /secret-like/);
  assert.throws(() => validateHostMarker(marker(m, [{ type: "native_runtime", name: "surface_domain", value: "chat", passed: true }]), m), /allowlisted/);
  assert.throws(() => validateHostMarker(marker(m, [{ type: "lifecycle", name: "state", value: "ready", passed: false }]), m), /malformed/);
  assert.throws(() => validateHostMarker({ ...marker(m), domain: "settings" }, m), /metadata/);
});

test("reduced runtime modes require computed policy, not AX or arbitrary values", () => {
  const motion = manifest({ accessibility: "reduced_motion" });
  assert.doesNotThrow(() => validateHostMarker(marker(motion, [{ type: "computed_style", name: "transition_duration", value: "0s", passed: true }]), motion));
  assert.throws(() => validateHostMarker(marker(motion, [{ type: "computed_style", name: "transition_duration", value: "1s", passed: true }]), motion), /allowlisted/);
  const transparency = manifest({ accessibility: "reduced_transparency" });
  assert.doesNotThrow(() => validateHostMarker(marker(transparency, [{ type: "computed_style", name: "backdrop_filter", value: "none", passed: true }]), transparency));
  assert.throws(() => validateHostMarker(marker(transparency, [{ type: "ax_snapshot", name: "role", value: "none", passed: true }]), transparency), /malformed/);
});

test("canonical runtime replay emits gate-shaped input set, receipt, and coverage", () => {
  const scratch = mkdtempSync(path.join(root, ".build", "runtime-replay-test-"));
  try {
    const m = manifest();
    const manifestPath = path.join(scratch, "coordinate.json");
    const inputPath = path.join(scratch, "runtime.json");
    const outputPath = path.join(scratch, "replayed.json");
    const outDir = path.join(scratch, "gate");
    const artifact = { schema: "omi.polish.runtime/v1", domain: m.domain, shell: m.shell, state: m.state, theme: m.theme, width: m.width, accessibility: m.accessibility, run_id: m.run_id, source_shas: m.source_shas, capture_class: m.capture_class, source_tier: m.source_tier, events: [{ type: "lifecycle", name: "state", value: m.state, passed: true }] };
    writeFileSync(manifestPath, `${JSON.stringify(m)}\n`);
    const artifactBytes = Buffer.from(`${JSON.stringify(artifact)}\n`);
    writeFileSync(inputPath, artifactBytes);
    writePreparation(path.join(scratch, "runtime-preparation-receipt.json"), m, inputPath, artifactBytes);
    const result = gateReplay(m, manifestPath, inputPath, outputPath, outDir);
    assert.equal(readFileSync(outputPath, "utf8"), readFileSync(inputPath, "utf8"));
    const receipt = JSON.parse(readFileSync(result.receiptPath, "utf8"));
    assert.equal(receipt.capture_class, "native_fixture");
    assert.equal(receipt.cwd_root, "core");
    assert.equal(receipt.artifact_created[`core:${path.relative(root, outputPath)}`], true);
    assert.ok(receipt.input_set.entries.some((entry) => entry.key.endsWith("runtime-preparation-receipt.json")));
    assert.ok(receipt.input_set.entries.some((entry) => entry.key.endsWith("macos-foreground-guard.mjs")));
    assert.match(receipt.argv.join(" "), /--emit-gate-records false/);
    const coverage = JSON.parse(readFileSync(result.coveragePath, "utf8"));
    assert.equal(coverage.coverage[0].kind, "runtime_trace");
    assert.equal(coverage.coverage[0].batch_id, receipt.batch_id);
    rmSync(outputPath, { force: true });
    const replay = spawnSync(process.execPath, receipt.argv.slice(1), { cwd: root, encoding: "utf8" });
    assert.equal(replay.status, 0, replay.stderr);
    assert.equal(existsSync(outputPath), true);
    const preparationPath = path.join(scratch, "runtime-preparation-receipt.json");
    const preparation = JSON.parse(readFileSync(preparationPath, "utf8"));
    writeFileSync(preparationPath, `${JSON.stringify({ ...preparation, foreground_custody: { ...preparation.foreground_custody, signal: "SIGKILL" } })}\n`);
    assert.throws(() => gateReplay(m, manifestPath, inputPath, path.join(scratch, "bad-signal.json"), outDir), /foreground custody/);
    writeFileSync(preparationPath, `${JSON.stringify({ ...preparation, command: { ...preparation.command, argv: [...preparation.command.argv, "--fixture", "settings"] } })}\n`);
    assert.throws(() => gateReplay(m, manifestPath, inputPath, path.join(scratch, "duplicate-flag.json"), outDir), /exact fixture launcher/);
    writeFileSync(preparationPath, `${JSON.stringify({ ...preparation, command: { ...preparation.command, argv: ["fixture"] } })}\n`);
    assert.throws(() => gateReplay(m, manifestPath, inputPath, path.join(scratch, "unguarded.json"), outDir), /guarded launcher/);
    writeFileSync(preparationPath, `${JSON.stringify({ ...preparation, artifact: { ...preparation.artifact, path: "other.json" } })}\n`);
    assert.throws(() => gateReplay(m, manifestPath, inputPath, path.join(scratch, "wrong-path.json"), outDir), /artifact authority/);
    writeFileSync(preparationPath, `${JSON.stringify(preparation)}\n`);
    writeFileSync(preparationPath, `${JSON.stringify({ ...preparation, foreground_custody: { ...preparation.foreground_custody, monitor_error: "changed" } })}\n`);
    assert.throws(() => gateReplay(m, manifestPath, inputPath, path.join(scratch, "custody-tampered.json"), outDir), /foreground custody/);
    writeFileSync(preparationPath, `${JSON.stringify(preparation)}\n`);
    writeFileSync(preparationPath, `${JSON.stringify({ ...preparation, artifact: { ...preparation.artifact, sha256: "0".repeat(64) } })}\n`);
    assert.throws(() => gateReplay(m, manifestPath, inputPath, path.join(scratch, "tampered.json"), outDir), /does not match/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});

test("recorded replay command is runnable without a host platform checkout", () => {
  const scratch = mkdtempSync(path.join(root, ".build", "runtime-cli-replay-test-"));
  try {
    const m = manifest();
    const manifestPath = path.join(scratch, "coordinate.json");
    const inputPath = path.join(scratch, "runtime.json");
    const outputPath = path.join(scratch, "replayed.json");
    const artifact = { schema: "omi.polish.runtime/v1", domain: m.domain, shell: m.shell, state: m.state, theme: m.theme, width: m.width, accessibility: m.accessibility, run_id: m.run_id, source_shas: m.source_shas, capture_class: m.capture_class, source_tier: m.source_tier, events: [{ type: "lifecycle", name: "state", value: m.state, passed: true }] };
    const artifactBytes = Buffer.from(`${JSON.stringify(artifact)}\n`);
    writeFileSync(manifestPath, `${JSON.stringify(m)}\n`); writeFileSync(inputPath, artifactBytes);
    writePreparation(path.join(scratch, "runtime-preparation-receipt.json"), m, inputPath, artifactBytes);
    const run = spawnSync(process.execPath, [producer, "--manifest", manifestPath, "--replay-input", inputPath, "--replay-output", outputPath, "--output-dir", path.join(scratch, "gate"), "--emit-gate-records", "false"], { cwd: root, encoding: "utf8" });
    assert.equal(run.status, 0, run.stderr);
    assert.match(run.stdout, /NATIVE_RUNTIME_REPLAY/);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});

test("iOS runtime replay binds and validates native foreground custody", () => {
  const scratch = mkdtempSync(path.join(root, ".build", "runtime-ios-custody-test-"));
  try {
    const m = manifest({ shell: "ios", surface_query: "polish=1&qa=chat&state=ready&platform=mobile&theme=dark&width=regular&accessibility=none&locale=en-US", device: { udid: "A".repeat(8) + "-AAAA-AAAA-AAAA-" + "A".repeat(12), model: "iPhone 17 Pro", orientation: "portrait" }, viewport: { width: 402, height: 874, scale: 3 } });
    const manifestPath = path.join(scratch, "coordinate.json"); const inputPath = path.join(scratch, "runtime.json"); const outputPath = path.join(scratch, "replayed.json");
    const artifact = { schema: "omi.polish.runtime/v1", domain: m.domain, shell: m.shell, state: m.state, theme: m.theme, width: m.width, accessibility: m.accessibility, run_id: m.run_id, source_shas: m.source_shas, capture_class: m.capture_class, source_tier: m.source_tier, events: [{ type: "lifecycle", name: "state", value: m.state, passed: true }] };
    const bytes = Buffer.from(`${JSON.stringify(artifact)}\n`); writeFileSync(manifestPath, `${JSON.stringify(m)}\n`); writeFileSync(inputPath, bytes);
    const preparationPath = path.join(scratch, "runtime-preparation-receipt.json"); writePreparation(preparationPath, m, inputPath, bytes);
    const result = gateReplay(m, manifestPath, inputPath, outputPath, path.join(scratch, "gate"));
    assert.ok(result.receipt.input_set.entries.some((entry) => entry.key.endsWith("macos-foreground-guard.mjs")));
    const preparation = JSON.parse(readFileSync(preparationPath, "utf8"));
    writeFileSync(preparationPath, `${JSON.stringify({ ...preparation, foreground_custody: { ...preparation.foreground_custody, monitor_error: "changed" } })}\n`);
    assert.throws(() => gateReplay(m, manifestPath, inputPath, path.join(scratch, "tampered.json"), path.join(scratch, "gate2")), /foreground custody/);
  } finally { rmSync(scratch, { recursive: true, force: true }); }
});
