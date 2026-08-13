import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { canonicalBatchId, classifySemanticProbeFailure, foregroundApplicationFromResults, lockedGuiBlock, probeUntilSemanticReady, semanticReadinessPolicy } from "../probes/native-semantic-evidence-batch.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const core = resolve(root, "../..");
const wrapper = join(root, "probes/native-semantic-evidence-batch.mjs");
const coreSha = execFileSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const platformSha = "1".repeat(40);

function lockedSessionSkipReason() {
  const front = spawnSync("/usr/bin/lsappinfo", ["front"], { encoding: "utf8", timeout: 5_000 });
  const identity = front.status === 0 ? front.stdout.trim().match(/ASN:0x[0-9a-f]+-0x[0-9a-f]+:/i)?.[0] : null;
  if (!identity) return false;
  const info = spawnSync("/usr/bin/lsappinfo", ["info", "-only", "name", "-app", identity], { encoding: "utf8", timeout: 5_000 });
  const bundle = spawnSync("/usr/bin/lsappinfo", ["info", "-only", "bundleID", "-app", identity], { encoding: "utf8", timeout: 5_000 });
  const observed = foregroundApplicationFromResults(front, info, bundle);
  return observed.name === "loginwindow" && observed.bundleId === "com.apple.loginwindow"
    ? "native semantic fixture execution requires an unlocked GUI session"
    : false;
}

const lockedSession = lockedSessionSkipReason();

test("AX readiness retries only transient semantic absence and records eventual success", () => {
  let clock = 0;
  let calls = 0;
  const sleeps = [];
  const attempts = [];
  const result = probeUntilSemanticReady({
    coordinate: { run_id: "semantic-readiness" }, runtimePid: 42,
    deadlineMilliseconds: 500, intervalMilliseconds: 100,
    now: () => clock, sleep: (milliseconds) => { sleeps.push(milliseconds); clock += milliseconds; },
    invoke: () => {
      calls += 1;
      return calls < 3
        ? { status: 1, stderr: "no-domain-landmark: memories", document: { error: "no-domain-landmark: memories" } }
        : { status: 0, stderr: "", document: { ready: true } };
    },
    validate: (document, pid) => { assert.equal(pid, 42); assert.equal(document.ready, true); },
    onAttempt: (attempt) => attempts.push(attempt),
  });
  assert.equal(result.document.ready, true);
  assert.equal(calls, 3);
  assert.deepEqual(sleeps, [100, 100]);
  assert.deepEqual(attempts.map((attempt) => attempt.outcome), ["retryable", "retryable", "ready"]);
  assert.equal(semanticReadinessPolicy.intervalMilliseconds, 100);
});

test("AX readiness fails closed at the deterministic deadline", () => {
  let clock = 0;
  let calls = 0;
  assert.throws(() => probeUntilSemanticReady({
    coordinate: { run_id: "semantic-deadline" }, runtimePid: 42,
    deadlineMilliseconds: 250, intervalMilliseconds: 100,
    now: () => clock, sleep: (milliseconds) => { clock += milliseconds; },
    invoke: () => { calls += 1; return { status: 1, stderr: "no-accessible-window: target has no observable native window", document: { error: "no-accessible-window: target has no observable native window" } }; },
    validate: () => { throw new Error("must not validate an errored probe"); },
  }), /semantic AX readiness deadline exceeded after 4 attempts/);
  assert.equal(calls, 4);
});

test("AX readiness does not retry identity or accessibility trust failures", () => {
  assert.equal(classifySemanticProbeFailure({ error: "target-identity-mismatch: wrong bundle" }).retryable, false);
  assert.equal(classifySemanticProbeFailure({ error: "accessibility-not-trusted: grant Accessibility access to this probe" }).retryable, false);
  assert.equal(classifySemanticProbeFailure({ error: "no-domain-landmark: memories" }).retryable, true);
  let calls = 0;
  assert.throws(() => probeUntilSemanticReady({
    coordinate: { run_id: "semantic-identity" }, runtimePid: 42,
    deadlineMilliseconds: 500, intervalMilliseconds: 100,
    invoke: () => { calls += 1; return { status: 1, stderr: "target-identity-mismatch: wrong bundle", document: { error: "target-identity-mismatch: wrong bundle" } }; },
    validate: () => {},
    sleep: () => { throw new Error("terminal identity failure must not sleep"); },
  }), /semantic probe failed: target-identity-mismatch/);
  assert.equal(calls, 1);
});

function manifest(kind = "ax_snapshot", captureClass = "native_fixture") {
  const coordinate = {
    schema: "omi.polish.matrix-coordinate/v1", kind, domain: "memories", shell: "macos", state: "ready", theme: "light", width: "regular",
    accessibility: kind === "ax_snapshot" ? "voiceover" : "keyboard", run_id: `semantic-${kind}`, capture_class: captureClass, source_tier: "native_shell",
    source_shas: { core: coreSha, platform: platformSha }, target: { pid: 999999, bundle_id: "me.omi.capture", process_name: "omi-on-polish-fixture" }, landmark: "memories",
    keys: kind === "ax_snapshot" ? [] : ["cmd+k", "escape"], expected_after: kind === "ax_snapshot" ? [] : ["command-palette-dialog", null],
  };
  return { schema: "omi.polish.matrix-manifest/v1", capture_class: captureClass, source_tier: "native_shell", coordinate_count: 1, source_shas: { core: coreSha, platform: platformSha }, coordinates: [coordinate] };
}

function fakeFixture(out) {
  const app = join(out, "omi-on-polish-fixture.app");
  const macos = join(app, "Contents/MacOS"); mkdirSync(macos, { recursive: true });
  writeFileSync(join(app, "Contents/Info.plist"), `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>me.omi.capture</string>
<key>CFBundleExecutable</key><string>omi-on-polish-fixture</string>
<key>LSUIElement</key><true/>
</dict></plist>\n`);
  const executable = join(macos, "omi-on-polish-fixture");
  writeFileSync(executable, `#!/usr/bin/env node
import fs from 'node:fs'; import path from 'node:path';
const runtime = process.env.OMI_SEMANTIC_RUNTIME_DIR;
const count = path.join(runtime, 'launch-count');
fs.writeFileSync(count, String((Number(fs.existsSync(count) ? fs.readFileSync(count, 'utf8') : 0)) + 1));
fs.writeFileSync(path.join(runtime, 'launcher-pid'), String(process.pid));
fs.writeFileSync(path.join(runtime, 'launch-env.json'), JSON.stringify({ semantic:process.env.OMI_SEMANTIC_WINDOW, headed:process.env.OMI_HEADED || null, query:process.env.OMI_SURFACE_QUERY, api:process.env.OMI_API_BASE_URL || null, token:process.env.OMI_API_TOKEN || null }));
process.stderr.write('display-mode: background-semantic\\n');
setInterval(() => {}, 1000);
`, { mode: 0o755 }); chmodSync(executable, 0o755);
  return app;
}

function fakeProbe(file, nodeName = "memories", pidDelta = 0) {
  writeFileSync(file, `#!/usr/bin/env node
const args = process.argv.slice(2); const value = key => args[args.indexOf('--' + key) + 1];
const kind = value('kind'); const keys = (value('keys') || '').split(',').filter(Boolean);
if (Number(value('pid')) === 999999) { process.stderr.write('external manifest PID was reused\\n'); process.exit(7); }
try { process.kill(Number(value('pid')), 0); } catch { process.stderr.write('runtime PID is not live\\n'); process.exit(8); }
if (value('bundle-id') !== 'me.omi.capture' || value('expected-bundle-id') !== 'me.omi.capture' || value('expected-process-name') !== 'omi-on-polish-fixture') { process.stderr.write('target identity is not exact\\n'); process.exit(11); }
if (kind === 'ax_snapshot' && (args.includes('--activate') || args.includes('--expect-after'))) { process.stderr.write('AX probes must stay background-only\\n'); process.exit(9); }
if (kind === 'keyboard_trace' && !args.includes('--activate')) { process.stderr.write('keyboard probe must activate explicitly\\n'); process.exit(10); }
const sourceCoreSha = value('source-core-sha'); const sourcePlatformSha = value('source-platform-sha');
const observedPid = Number(value('pid')) + ${pidDelta};
const out = { schema:'omi.native-semantic-evidence.v2', shell:'macos', runId:value('run-id'), targetPid:observedPid, coordinate:value('coordinate'), sourceCoreSha, sourcePlatformSha, axTrusted:true, matrixEligible:true, domainLandmarkFound:true, evidenceClass:kind === 'keyboard_trace' ? 'native_keyboard_trace' : 'native_ax_snapshot', target:{pid:observedPid, bundleId:value('bundle-id'), processNameBound:true, expectedPid:observedPid, expectedBundleId:value('expected-bundle-id'), bound:true}, nodes:[{role:'AXHeading',name:${JSON.stringify(nodeName)}}], keys:keys.map(key => ({key,targetConsumed:true})), windows:[], focusRestored:kind === 'keyboard_trace' ? true : null, frontmostRestored:kind === 'keyboard_trace' ? true : null};
process.stdout.write(JSON.stringify(out));
`, { mode: 0o755 });
  chmodSync(file, 0o755);
}

function prepareArgs(matrix, out, probe, app) {
  return [wrapper, "--manifest", matrix, "--out-root", out, "--probe", probe, "--fixture-app", app, "--prepare"];
}

test("semantic batch emits exact AX coverage and immutable prepared inputs", { skip: lockedSession }, () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-batch-"));
  try {
    const out = join(root, ".build", `semantic-batch-test-${process.pid}`); mkdirSync(out, { recursive: true });
    const probe = join(out, "fake-probe.mjs"); fakeProbe(probe); const app = fakeFixture(out);
    const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest()));
    const prepared = spawnSync(process.execPath, prepareArgs(matrix, out, probe, app), { encoding: "utf8" });
    assert.equal(prepared.status, 0, prepared.stderr); const preparedPath = join(out, "prepared-input-set.json");
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", preparedPath, "--replay-proof"], { encoding: "utf8" });
    assert.equal(captured.status, 0, `${captured.stdout}${captured.stderr}`); assert.match(captured.stdout, /NATIVE_SEMANTIC_BATCH_COMPLETE members=1/);
    const firstResultBytes = readFileSync(join(out, "batch-result.json")); const firstEvidenceBytes = readFileSync(join(out, "captures/macos/semantic-ax_snapshot.json")); const firstSidecarBytes = readFileSync(join(out, "captures/macos/semantic-ax_snapshot.json.sidecar.json"));
    const result = JSON.parse(firstResultBytes.toString("utf8")); assert.ok(result.input_set.entries.length >= 6); assert.equal(result.members.m0000.coordinate[0], "ax_snapshot");
    const replayed = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", preparedPath, "--replay-proof"], { encoding: "utf8" });
    assert.equal(replayed.status, 0, `${replayed.stdout}${replayed.stderr}`); assert.deepEqual(readFileSync(join(out, "batch-result.json")), firstResultBytes); assert.deepEqual(readFileSync(join(out, "captures/macos/semantic-ax_snapshot.json")), firstEvidenceBytes); assert.deepEqual(readFileSync(join(out, "captures/macos/semantic-ax_snapshot.json.sidecar.json")), firstSidecarBytes);
    const runtime = join(out, "runtime/semantic-ax_snapshot");
    assert.equal(readFileSync(join(runtime, "launch-count"), "utf8"), "2", "one --replay-proof capture launches the prepared app twice");
    assert.notEqual(Number(readFileSync(join(runtime, "launcher-pid"), "utf8")), 999999, "the manifest PID is never used as a target");
    const readiness = JSON.parse(readFileSync(join(runtime, "semantic-readiness.json"), "utf8"));
    assert.equal(readiness.schema, "omi.native-semantic-readiness/v1");
    assert.equal(readiness.status, "ready");
    assert.equal(readiness.policy.intervalMilliseconds, 100);
    assert.ok(readiness.attempts.length >= 1);
    const launchEnv = JSON.parse(readFileSync(join(runtime, "launch-env.json"), "utf8"));
    assert.deepEqual(launchEnv, { semantic: "1", headed: null, query: "polish=1&qa=memories&state=ready&platform=desktop&theme=light&width=regular&accessibility=voiceover&locale=en-US", api: null, token: null });
    const sidecar = readFileSync(join(out, "captures/macos/semantic-ax_snapshot.json.sidecar.json"), "utf8");
    assert.doesNotMatch(sidecar, /"pid"\s*:/); assert.doesNotMatch(firstResultBytes.toString("utf8"), /"pid"\s*:/);
    writeFileSync(join(out, "batch-result.json"), JSON.stringify({ ...result, replay_proof: false }));
    const unproved = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--assemble-receipt", "--result-path", join(out, "batch-result.json")], { encoding: "utf8" });
    assert.equal(unproved.status, 2); assert.match(unproved.stderr, /lacks a completed replay proof/);
    writeFileSync(join(out, "batch-result.json"), JSON.stringify({ ...result, replay_proof: true, replay_attestation: null }));
    const forgedProof = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--assemble-receipt", "--result-path", join(out, "batch-result.json")], { encoding: "utf8" });
    assert.equal(forgedProof.status, 2); assert.match(forgedProof.stderr, /replay attestation|independent replay/);
    writeFileSync(join(out, "batch-result.json"), JSON.stringify({ ...result, command: `${result.command} 'ignored'` }));
    const forgedCommand = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--assemble-receipt", "--result-path", join(out, "batch-result.json")], { encoding: "utf8" });
    assert.equal(forgedCommand.status, 2); assert.match(forgedCommand.stderr, /exact replay-proof capture invocation/);
    writeFileSync(join(out, "batch-result.json"), firstResultBytes);
    for (const tamperedAuthority of [
      { ...result.authority, fixture: false },
      { ...result.authority, focus_policy: { ...result.authority.focus_policy, ax: "monitor-disabled" } },
    ]) {
      writeFileSync(join(out, "batch-result.json"), JSON.stringify({ ...result, authority: tamperedAuthority }));
      const tampered = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--assemble-receipt", "--result-path", join(out, "batch-result.json")], { encoding: "utf8" });
      assert.equal(tampered.status, 2);
      assert.match(tampered.stderr, /authority does not match the prepared fixture\/focus authority/);
    }
    writeFileSync(join(out, "batch-result.json"), firstResultBytes);
    const assembled = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--assemble-receipt", "--result-path", join(out, "batch-result.json")], { encoding: "utf8" });
    assert.equal(assembled.status, 0, assembled.stderr); const receiptPath = assembled.stdout.match(/file=(.+\.receipt\.json)/)?.[1]; assert.ok(receiptPath);
    const receiptBytes = readFileSync(join(core, receiptPath), "utf8"); const receipt = JSON.parse(receiptBytes); assert.match(receipt.batch_id, /^batch-v1-[0-9a-f]{64}$/); assert.equal(receipt.coverage[0].command_receipt.capture_class, "native_fixture"); assert.doesNotMatch(receiptBytes, /"pid"\s*:/);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
    rmSync(join(root, ".build", `semantic-batch-test-${process.pid}`), { recursive: true, force: true });
  }
});

test("semantic batch identity binds the exact authority", () => {
  const members = { m0000: { run_id: "semantic-ax_snapshot" } };
  const authority = { fixture: true, focus_policy: { ax: "guarded" } };
  assert.notEqual(
    canonicalBatchId("input-v1-test", "capture", members, authority),
    canonicalBatchId("input-v1-test", "capture", members, { ...authority, fixture: false }),
  );
});

test("foreground classification fails closed and identifies a locked loginwindow", () => {
  const front = { status: 0, stdout: "ASN:0x0-0x1001:\n" };
  const bundle = { status: 0, stdout: '"CFBundleIdentifier"="com.apple.loginwindow"\n' };
  assert.deepEqual(foregroundApplicationFromResults(front, { status: 0, stdout: '"LSDisplayName"="loginwindow"\n' }, bundle), { identity: "ASN:0x0-0x1001:", name: "loginwindow", bundleId: "com.apple.loginwindow" });
  const blocked = lockedGuiBlock({ identity: "ASN:0x0-0x1001:", name: "loginwindow", bundleId: "com.apple.loginwindow" }, { core: coreSha, platform: platformSha }, manifest().coordinates);
  assert.equal(blocked.status, "blocked_gui_locked");
  assert.equal(lockedGuiBlock({ identity: "ASN:0x0-0x1234:", name: "Codex", bundleId: "com.openai.codex" }, { core: coreSha, platform: platformSha }, manifest().coordinates), null);
  assert.throws(() => foregroundApplicationFromResults({ status: 1, stdout: "" }, { status: 0, stdout: "" }, bundle), /identity is unavailable/);
  assert.throws(() => foregroundApplicationFromResults(front, { status: 1, stdout: "" }, bundle), /metadata is unavailable/);
  assert.throws(() => foregroundApplicationFromResults(front, { status: 0, stdout: '"LSDisplayName"="Codex"\n' }, { status: 1, stdout: "" }), /bundle metadata is unavailable/);
});

test("prepared semantic ranges are immutable and cannot be widened on replay", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-range-"));
  try {
    const out = join(root, ".build", `semantic-range-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe); const app = fakeFixture(out); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest()));
    const preparedPath = join(out, "prepared-input-set.json"); const prepared = spawnSync(process.execPath, prepareArgs(matrix, out, probe, app), { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const descriptor = JSON.parse(readFileSync(preparedPath, "utf8")); descriptor.offset = 1; writeFileSync(preparedPath, JSON.stringify(descriptor));
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", preparedPath], { encoding: "utf8" }); assert.equal(captured.status, 2); assert.match(captured.stderr, /prepared semantic input set is stale/);
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-range-test-${process.pid}`), { recursive: true, force: true }); }
});

test("semantic batch rejects a probe document bound to any PID except the launched child", { skip: lockedSession }, () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-target-"));
  try {
    const out = join(root, ".build", `semantic-target-test-${process.pid}`); mkdirSync(out, { recursive: true });
    const probe = join(out, "fake-probe.mjs"); fakeProbe(probe, "memories", 1); const app = fakeFixture(out);
    const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest()));
    const prepared = spawnSync(process.execPath, prepareArgs(matrix, out, probe, app), { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", join(out, "prepared-input-set.json")], { encoding: "utf8" });
    assert.equal(captured.status, 2); assert.match(captured.stderr, /probe target binding is not exact/);
    const launchedPid = Number(readFileSync(join(out, "runtime/semantic-ax_snapshot/launcher-pid"), "utf8"));
    assert.throws(() => process.kill(launchedPid, 0), /ESRCH/);
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-target-test-${process.pid}`), { recursive: true, force: true }); }
});

test("keyboard trace requires each observed transition and Escape restoration", { skip: lockedSession }, () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-keyboard-"));
  try {
    const out = join(root, ".build", `semantic-keyboard-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe); const app = fakeFixture(out); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest("keyboard_trace")));
    const prepared = spawnSync(process.execPath, prepareArgs(matrix, out, probe, app), { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", join(out, "prepared-input-set.json")], { encoding: "utf8", env: { ...process.env, OMI_ALLOW_TEMPORARY_FOCUS: "1" } }); assert.equal(captured.status, 0, `${captured.stdout}${captured.stderr}`);
    const evidence = JSON.parse(readFileSync(join(out, "captures/macos/semantic-keyboard_trace.json"), "utf8")); assert.equal(evidence.schema, "omi.polish.keyboard/v1"); assert.deepEqual(evidence.steps.map((step) => step.result), ["observed", "observed"]); assert.equal(evidence.steps.at(-1).action, "restore-focus");
    const sidecar = JSON.parse(readFileSync(join(out, "captures/macos/semantic-keyboard_trace.json.sidecar.json"), "utf8")); assert.equal(sidecar.frontmost_restored, true);
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-keyboard-test-${process.pid}`), { recursive: true, force: true }); }
});

test("keyboard batch is focus-safe by default and requires explicit operator consent", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-focus-block-"));
  try {
    const out = join(root, ".build", `semantic-focus-block-test-${process.pid}`); mkdirSync(out, { recursive: true });
    const invoked = join(out, "probe-invoked");
    const probe = join(out, "fake-probe.mjs");
    writeFileSync(probe, `#!/usr/bin/env node\nrequire('node:fs').writeFileSync(${JSON.stringify(invoked)}, 'yes');\n`, { mode: 0o755 }); chmodSync(probe, 0o755);
    const app = fakeFixture(out); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest("keyboard_trace")));
    const prepared = spawnSync(process.execPath, prepareArgs(matrix, out, probe, app), { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", join(out, "prepared-input-set.json")], { encoding: "utf8", env: { ...process.env, OMI_ALLOW_TEMPORARY_FOCUS: "0" } });
    assert.equal(captured.status, 3, `${captured.stdout}${captured.stderr}`);
    const blocked = JSON.parse(captured.stdout); assert.equal(blocked.status, "blocked_user_focus");
    assert.equal(existsSync(invoked), false, "focus-blocked batches must not start the native probe");
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-focus-block-test-${process.pid}`), { recursive: true, force: true }); }
});

test("AX batch rejects a probe that tries to serialize user text", { skip: lockedSession }, () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-redaction-"));
  try {
    const out = join(root, ".build", `semantic-redaction-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe, "Created by David"); const app = fakeFixture(out); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest()));
    const prepared = spawnSync(process.execPath, prepareArgs(matrix, out, probe, app), { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", join(out, "prepared-input-set.json")], { encoding: "utf8" }); assert.equal(captured.status, 2); assert.match(captured.stderr, /no redacted role\/name nodes/);
    const launchedPid = Number(readFileSync(join(out, "runtime/semantic-ax_snapshot/launcher-pid"), "utf8"));
    assert.throws(() => process.kill(launchedPid, 0), /ESRCH/, "the exact fixture child is terminated when the probe fails");
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-redaction-test-${process.pid}`), { recursive: true, force: true }); }
});

test("semantic producer fails closed for native_live manifests instead of probing an external PID", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-locked-"));
  try {
    const out = join(root, ".build", `semantic-locked-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe); const app = fakeFixture(out); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest("ax_snapshot", "native_live")));
    const prepared = spawnSync(process.execPath, prepareArgs(matrix, out, probe, app), { encoding: "utf8" }); assert.equal(prepared.status, 2); assert.match(prepared.stderr, /requires native_fixture authority/);
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-locked-test-${process.pid}`), { recursive: true, force: true }); }
});
