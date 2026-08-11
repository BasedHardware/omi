import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const core = resolve(root, "../..");
const wrapper = join(root, "probes/native-semantic-evidence-batch.mjs");
const coreSha = execFileSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
const platformSha = "1".repeat(40);

function manifest(kind = "ax_snapshot", captureClass = "native_fixture") {
  const coordinate = {
    schema: "omi.polish.matrix-coordinate/v1", kind, domain: "memories", shell: "macos", state: "ready", theme: "light", width: "regular",
    accessibility: kind === "ax_snapshot" ? "voiceover" : "keyboard", run_id: `semantic-${kind}`, capture_class: captureClass, source_tier: "native_shell",
    source_shas: { core: coreSha, platform: platformSha }, target: { pid: process.pid, bundle_id: "me.omi.capture", process_name: "omi-on-polish-fixture" }, landmark: "memories",
    keys: kind === "ax_snapshot" ? [] : ["cmd+k", "escape"], expected_after: kind === "ax_snapshot" ? [] : ["command-palette-dialog", null],
  };
  return { schema: "omi.polish.matrix-manifest/v1", capture_class: captureClass, source_tier: "native_shell", coordinate_count: 1, source_shas: { core: coreSha, platform: platformSha }, coordinates: [coordinate] };
}

function fakeProbe(file, nodeName = "memories") {
  writeFileSync(file, `#!/usr/bin/env node
const args = process.argv.slice(2); const value = key => args[args.indexOf('--' + key) + 1];
const kind = value('kind'); const keys = (value('keys') || '').split(',').filter(Boolean);
if (kind === 'ax_snapshot' && (args.includes('--activate') || args.includes('--expect-after'))) { process.stderr.write('AX probes must stay background-only\\n'); process.exit(9); }
if (kind === 'keyboard_trace' && !args.includes('--activate')) { process.stderr.write('keyboard probe must activate explicitly\\n'); process.exit(10); }
const sourceCoreSha = value('source-core-sha'); const sourcePlatformSha = value('source-platform-sha');
const out = { schema:'omi.native-semantic-evidence.v2', shell:'macos', runId:value('run-id'), targetPid:Number(value('pid')), coordinate:value('coordinate'), sourceCoreSha, sourcePlatformSha, axTrusted:true, matrixEligible:true, domainLandmarkFound:true, evidenceClass:kind === 'keyboard_trace' ? 'native_keyboard_trace' : 'native_ax_snapshot', target:{pid:Number(value('pid')), bundleId:value('bundle-id'), processNameBound:true, expectedPid:Number(value('pid')), expectedBundleId:value('expected-bundle-id'), bound:true}, nodes:[{role:'AXHeading',name:${JSON.stringify(nodeName)}}], keys:keys.map(key => ({key,targetConsumed:true})), windows:[], focusRestored:kind === 'keyboard_trace' ? true : null, frontmostRestored:kind === 'keyboard_trace' ? true : null};
process.stdout.write(JSON.stringify(out));
`, { mode: 0o755 });
  chmodSync(file, 0o755);
}

test("semantic batch emits exact AX coverage and immutable prepared inputs", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-batch-"));
  try {
    const out = join(root, ".build", `semantic-batch-test-${process.pid}`); mkdirSync(out, { recursive: true });
    const probe = join(out, "fake-probe.mjs"); fakeProbe(probe);
    const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest()));
    const prepared = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--probe", probe, "--prepare"], { encoding: "utf8" });
    assert.equal(prepared.status, 0, prepared.stderr); const preparedPath = join(out, "prepared-input-set.json");
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", preparedPath, "--replay-proof"], { encoding: "utf8" });
    assert.equal(captured.status, 0, `${captured.stdout}${captured.stderr}`); assert.match(captured.stdout, /NATIVE_SEMANTIC_BATCH_COMPLETE members=1/);
    const firstResultBytes = readFileSync(join(out, "batch-result.json")); const firstEvidenceBytes = readFileSync(join(out, "captures/macos/semantic-ax_snapshot.json"));
    const result = JSON.parse(firstResultBytes.toString("utf8")); assert.equal(result.input_set.entries.length, 4); assert.equal(result.members.m0000.coordinate[0], "ax_snapshot");
    const replayed = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", preparedPath, "--replay-proof"], { encoding: "utf8" });
    assert.equal(replayed.status, 0, `${replayed.stdout}${replayed.stderr}`); assert.deepEqual(readFileSync(join(out, "batch-result.json")), firstResultBytes); assert.deepEqual(readFileSync(join(out, "captures/macos/semantic-ax_snapshot.json")), firstEvidenceBytes);
    const assembled = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--assemble-receipt", "--result-path", join(out, "batch-result.json")], { encoding: "utf8" });
    assert.equal(assembled.status, 0, assembled.stderr); const receiptPath = assembled.stdout.match(/file=(.+\.receipt\.json)/)?.[1]; assert.ok(receiptPath);
    const receipt = JSON.parse(readFileSync(join(core, receiptPath), "utf8")); assert.match(receipt.batch_id, /^batch-v1-[0-9a-f]{64}$/); assert.equal(receipt.coverage[0].command_receipt.capture_class, "native_fixture");
  } finally {
    rmSync(scratch, { recursive: true, force: true });
    rmSync(join(root, ".build", `semantic-batch-test-${process.pid}`), { recursive: true, force: true });
  }
});

test("prepared semantic ranges are immutable and cannot be widened on replay", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-range-"));
  try {
    const out = join(root, ".build", `semantic-range-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest()));
    const preparedPath = join(out, "prepared-input-set.json"); const prepared = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--probe", probe, "--prepare"], { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const descriptor = JSON.parse(readFileSync(preparedPath, "utf8")); descriptor.offset = 1; writeFileSync(preparedPath, JSON.stringify(descriptor));
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", preparedPath], { encoding: "utf8" }); assert.equal(captured.status, 2); assert.match(captured.stderr, /prepared semantic input set is stale/);
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-range-test-${process.pid}`), { recursive: true, force: true }); }
});

test("keyboard trace requires each observed transition and Escape restoration", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-keyboard-"));
  try {
    const out = join(root, ".build", `semantic-keyboard-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest("keyboard_trace")));
    const prepared = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--probe", probe, "--prepare"], { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", join(out, "prepared-input-set.json")], { encoding: "utf8" }); assert.equal(captured.status, 0, `${captured.stdout}${captured.stderr}`);
    const evidence = JSON.parse(readFileSync(join(out, "captures/macos/semantic-keyboard_trace.json"), "utf8")); assert.equal(evidence.schema, "omi.polish.keyboard/v1"); assert.deepEqual(evidence.steps.map((step) => step.result), ["observed", "observed"]); assert.equal(evidence.steps.at(-1).action, "restore-focus");
    const sidecar = JSON.parse(readFileSync(join(out, "captures/macos/semantic-keyboard_trace.json.sidecar.json"), "utf8")); assert.equal(sidecar.frontmost_restored, true);
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-keyboard-test-${process.pid}`), { recursive: true, force: true }); }
});

test("AX batch rejects a probe that tries to serialize user text", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-redaction-"));
  try {
    const out = join(root, ".build", `semantic-redaction-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe, "Created by David"); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest()));
    const prepared = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--probe", probe, "--prepare"], { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", join(out, "prepared-input-set.json")], { encoding: "utf8" }); assert.equal(captured.status, 2); assert.match(captured.stderr, /no redacted role\/name nodes/);
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-redaction-test-${process.pid}`), { recursive: true, force: true }); }
});

test("live semantic capture reports locked GUI as blocked instead of fabricating matrix evidence", () => {
  const front = spawnSync("lsappinfo", ["front"], { encoding: "utf8" });
  if (front.status !== 0) return;
  const token = `${front.stdout || ""} ${front.stderr || ""}`.trim(); const details = [token, token.replace(/^ASN:/, "")].flatMap((value) => [spawnSync("lsappinfo", ["info", "-only", "name", "-app", value], { encoding: "utf8" }), spawnSync("lsappinfo", ["info", "-only", "bundleid", "-app", value], { encoding: "utf8" })]).map((result) => `${result.stdout || ""} ${result.stderr || ""}`).join(" ").toLowerCase();
  if (!`${token} ${details}`.includes("loginwindow") && !details.includes("com.apple.loginwindow")) return;
  const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-locked-"));
  try {
    const out = join(root, ".build", `semantic-locked-test-${process.pid}`); mkdirSync(out, { recursive: true }); const probe = join(out, "fake-probe.mjs"); fakeProbe(probe); const matrix = join(out, "matrix.json"); writeFileSync(matrix, JSON.stringify(manifest("ax_snapshot", "native_live")));
    const prepared = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--probe", probe, "--prepare"], { encoding: "utf8" }); assert.equal(prepared.status, 0, prepared.stderr);
    const captured = spawnSync(process.execPath, [wrapper, "--manifest", matrix, "--out-root", out, "--prepared-input-set", join(out, "prepared-input-set.json")], { encoding: "utf8" }); assert.equal(captured.status, 3); assert.equal(JSON.parse(captured.stdout).status, "blocked_gui_locked");
  } finally { rmSync(scratch, { recursive: true, force: true }); rmSync(join(root, ".build", `semantic-locked-test-${process.pid}`), { recursive: true, force: true }); }
});
