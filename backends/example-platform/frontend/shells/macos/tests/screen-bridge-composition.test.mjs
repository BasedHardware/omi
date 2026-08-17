import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function hasSwiftc() {
  try { execFileSync("swiftc", ["--version"], { stdio: "ignore" }); return true; }
  catch { return false; }
}

const HARNESS = String.raw`
import Foundation

final class FakeScreenHandlers: BridgeHandling, @unchecked Sendable {
  func startCapture(_ params: StartCaptureParams) async throws -> StartCaptureResult {
    StartCaptureResult(sessionId: "audio", state: .idle)
  }
  func readSetting(_ params: ReadSettingParams) async throws -> ReadSettingResult {
    ReadSettingResult(key: params.key, value: nil)
  }
  func openExternal(_ params: OpenExternalParams) async throws -> OpenExternalResult {
    OpenExternalResult(opened: false)
  }
  func screenStart(_ params: ScreenEmptyParams) async throws -> ScreenStartResult {
    ScreenStartResult(sessionId: "sess-1", state: .recording)
  }
  func screenStop(_ params: ScreenEmptyParams) async throws -> ScreenStopResult {
    ScreenStopResult(state: .idle)
  }
  func screenStatus(_ params: ScreenEmptyParams) async throws -> ScreenStatusResult {
    ScreenStatusResult(
      state: .idle, reason: nil, permission: .undetermined, framesStored: 0,
      bytesOnDisk: nil, lastCaptureAt: nil)
  }
  func screenFrameImage(_ params: ScreenFrameImageParams) async throws -> ScreenFrameImageResult {
    ScreenFrameImageResult(pngBase64: "AA==", width: 1, height: 1)
  }
  func screenExclusionsList(_ params: ScreenEmptyParams) async throws -> ScreenExclusionsListResult {
    ScreenExclusionsListResult(bundleIds: ["com.1password.1password"])
  }
  func screenExclusionsSet(_ params: ScreenExclusionsSetParams) async throws -> ScreenExclusionsSetResult {
    ScreenExclusionsSetResult(bundleIds: params.bundleIds, retiredFrameRefs: ["retired-1"])
  }
  func screenRetentionSet(_ params: ScreenRetentionSetParams) async throws -> ScreenRetentionSetResult {
    ScreenRetentionSetResult(days: ScreenRetentionPolicy.normalize(params.days), retiredFrameRefs: [])
  }
  func screenRebuildIndex(_ params: ScreenEmptyParams) async throws -> ScreenRebuildIndexResult {
    ScreenRebuildIndexResult(frames: 0, chunks: 0)
  }
  func screenRequestPermission(_ params: ScreenEmptyParams) async throws -> ScreenPermissionResult {
    ScreenPermissionResult(permission: .undetermined)
  }
  func screenOpenSettings(_ params: ScreenEmptyParams) async throws -> ScreenOpenSettingsResult {
    ScreenOpenSettingsResult(opened: true)
  }
}

func extract(_ js: String, _ key: String) -> String? {
  guard let data = js.data(using: .utf8) else { return nil }
  // dispatch returns window.__OmiShellBridge.__reply({...});
  guard let start = js.firstIndex(of: "{"), let end = js.lastIndex(of: "}") else { return nil }
  let json = String(js[start...end])
  guard let payload = json.data(using: .utf8),
    let obj = try? JSONSerialization.jsonObject(with: payload) as? [String: Any]
  else { return nil }
  if key == "ok" {
    if let n = obj["ok"] as? NSNumber { return n.boolValue ? "true" : "false" }
    return String(describing: obj["ok"] ?? "")
  }
  if key == "error" { return obj["error"] as? String }
  if let result = obj["result"] as? [String: Any] {
    if key == "opened" {
      if let n = result[key] as? NSNumber { return n.boolValue ? "true" : "false" }
    }
    if let n = result[key] as? NSNumber { return String(n.intValue) }
    if let s = result[key] as? String { return s }
    if let v = result[key] { return String(describing: v) }
  }
  return obj[key].map { String(describing: $0) }
}

let dispatcher = BridgeDispatcher(handler: FakeScreenHandlers())

func send(_ method: String, _ params: String) async -> String {
  let raw = "{\"id\":\"t1\",\"method\":\"\(method)\",\"params\":\(params)}"
  return await dispatcher.dispatch(raw: Data(raw.utf8))
}

func run() async {
  let start = await send("screen.start", "{}")
  print("START-OK=\(extract(start, "ok") ?? "?")")
  print("START-STATE=\(extract(start, "state") ?? "?")")
  print("START-SESSION=\(extract(start, "sessionId") ?? "?")")
  let stop = await send("screen.stop", "{}")
  print("STOP-STATE=\(extract(stop, "state") ?? "?")")
  let status = await send("screen.status", "{}")
  print("STATUS-PERM=\(extract(status, "permission") ?? "?")")
  print("STATUS-RAW=\(status)")
  let img = await send("screen.frameImage", "{\"frameRef\":\"abc\"}")
  print("FRAME-W=\(extract(img, "width") ?? "?")")
  let list = await send("screen.exclusionsList", "{}")
  print("EXCL-LIST=\(list.contains("com.1password.1password"))")
  let set = await send("screen.exclusionsSet", "{\"bundleIds\":[\"com.bitwarden.desktop\"]}")
  print("EXCL-SET=\(set)")
  let ret = await send("screen.retentionSet", "{\"days\":99}")
  print("RET-DAYS=\(extract(ret, "days") ?? "?")")
  let rebuild = await send("screen.rebuildIndex", "{}")
  print("REBUILD-FRAMES=\(extract(rebuild, "frames") ?? "?")")
  let perm = await send("screen.requestPermission", "{}")
  print("REQ-PERM=\(extract(perm, "permission") ?? "?")")
  let open = await send("screen.openSettings", "{}")
  print("OPENED=\(extract(open, "opened") ?? "?")")
  let unknown = await send("screen.nope", "{}")
  print("UNKNOWN-OK=\(extract(unknown, "ok") ?? "?")")
  print("UNKNOWN-ERR=\((extract(unknown, "error") ?? "").contains("unknownMethod"))")
  let event = BridgeDispatcher.emitScreenStatus(
    ScreenStatusEvent(
      state: .recording, reason: nil, permission: .granted, framesStored: 1,
      bytesOnDisk: nil, lastCaptureAt: nil))
  print("EVENT-NAME=\(event.contains("screen.status"))")
  print("EVENT-CHANNEL=\(event.contains("__OmiShellBridge.__event"))")
}

let lock = DispatchSemaphore(value: 0)
Task {
  await run()
  lock.signal()
}
lock.wait()
`;

test(
  "screen bridge verbs dispatch by their fixed dotted names and unknown verbs fail honestly",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    // red-proof: rename screen.start in the dispatcher switch, or map unknown
    // methods to a hang / empty reply, and START-STATE or UNKNOWN-OK fails.
    const scratch = mkdtempSync(join(tmpdir(), "omi-screen-bridge-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(root, "shell/Sources/OmiShell/Bridge.generated.swift"),
        join(root, "shell/Sources/OmiShell/ScreenPolicy.swift"),
        main,
        "-framework", "Foundation",
      ]);
      const output = execFileSync(binary, { encoding: "utf8" });
      assert.match(output, /^START-OK=true$/m);
      assert.match(output, /^START-STATE=recording$/m);
      assert.match(output, /^START-SESSION=sess-1$/m);
      assert.match(output, /^STOP-STATE=idle$/m);
      assert.match(output, /^STATUS-PERM=undetermined$/m);
      assert.equal(output.includes("STATUS-RAW=") && !/STATUS-RAW=.*bytesOnDisk/.test(output), true, output);
      assert.match(output, /^FRAME-W=1$/m);
      assert.match(output, /^EXCL-LIST=true$/m);
      assert.match(output, /retired-1/);
      assert.match(output, /^RET-DAYS=0$/m);
      assert.match(output, /^REBUILD-FRAMES=0$/m);
      assert.match(output, /^REQ-PERM=undetermined$/m);
      assert.match(output, /^OPENED=true$/m);
      assert.match(output, /^UNKNOWN-OK=false$/m);
      assert.match(output, /^UNKNOWN-ERR=true$/m);
      assert.match(output, /^EVENT-NAME=true$/m);
      assert.match(output, /^EVENT-CHANNEL=true$/m);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
