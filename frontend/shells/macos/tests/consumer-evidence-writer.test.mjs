import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "shell/Sources/OmiShell/ConsumerEvidence.swift");
const validator = resolve(root, "../tools/validate-consumer-evidence.mjs");

test("macOS evidence driver authors through the rendered composer and waits for canonical admission", () => {
  // red-proof: restore the visit-only Chat branch; one of the author, submit,
  // or rendered admission-baseline assertions disappears.
  const driver = readFileSync(
    join(root, "shell/Sources/OmiShell/ConsumerEvidenceDriver.swift"),
    "utf8",
  );
  assert.match(driver, /C3b3 deterministic synthetic Chat evidence\./);
  assert.match(driver, /textarea\.chat-draft/);
  assert.match(driver, /button\.chat-send/);
  assert.match(driver, /consumerChatAdmissionCount/);
  assert.ok(driver.includes("admitted <= \\#(baseline)"));
  assert.match(driver, /routeDriveState\.chatAdmissionBaseline = number\.intValue/);
  assert.match(driver, /routeDriveState\.chatSubmitted = value as\? Bool == true/);
  assert.match(driver, /pageDidFinish\(_ navigation: WKNavigation\?\)/);
  assert.match(driver, /routeDriveState\.acceptFinished\(navigation\)/);
  assert.match(driver, /routeDriveState\.begin\(navigation\)/);
  const finishBody = driver.match(/func pageDidFinish[\s\S]*?\n  \}/u)?.[0] ?? "";
  assert.doesNotMatch(finishBody, /\.begin\(|listenStartRequested = false|chatAdmissionBaseline = nil|chatSubmitted = false/);
});

function hasSwiftc() {
  try { execFileSync("swiftc", ["--version"], { stdio: "ignore" }); return true; }
  catch { return false; }
}

const HARNESS = String.raw`
import Foundation

var failed = false
func check(_ name: String, _ condition: @autoclosure () throws -> Bool) {
  do {
    let ok = try condition()
    print(ok ? "OK: \(name)" : "FAIL: \(name)")
    if !ok { failed = true }
  } catch {
    print("FAIL: \(name) threw \(error)")
    failed = true
  }
}
func rejects(_ name: String, _ operation: () throws -> Void) {
  do { try operation(); print("FAIL: \(name)"); failed = true }
  catch { print("OK: \(name)") }
}

let scratch = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let result = scratch.appendingPathComponent("result.json")
let shellStamp = scratch.appendingPathComponent("shell.json")
let surfaceStamp = scratch.appendingPathComponent("surface.json")
try! Data("{\"artifact\":\"macos-app\",\"treeHash\":\"1111111111111111111111111111111111111111\"}".utf8).write(to: shellStamp)
try! Data("{\"artifact\":\"surfaces-dist\",\"treeHash\":\"2222222222222222222222222222222222222222\"}".utf8).write(to: surfaceStamp)
let hashes = try! ConsumerEvidenceTreeHashes.load(shellStamp: shellStamp, surfaceStamp: surfaceStamp)

var routeDriveState = ConsumerEvidenceRouteDriveState()
let listenNavigation = NSObject()
let chatNavigation = NSObject()
check("owned Listen navigation begins", routeDriveState.begin(listenNavigation))
routeDriveState.listenStartRequested = true
check("owned Listen completion advances", routeDriveState.acceptFinished(listenNavigation))
check("duplicate Listen completion cannot replay", !routeDriveState.acceptFinished(listenNavigation))
check("duplicate Listen completion preserves action state", routeDriveState.listenStartRequested)
check("owned Chat navigation begins", routeDriveState.begin(chatNavigation))
check("new owned route resets prior action state", !routeDriveState.listenStartRequested)
routeDriveState.chatAdmissionBaseline = 2
routeDriveState.chatSubmitted = true
check("late Listen completion cannot reset Chat", !routeDriveState.acceptFinished(listenNavigation))
check("late Listen completion preserves Chat submission", routeDriveState.chatAdmissionBaseline == 2 && routeDriveState.chatSubmitted)
check("next owned Chat completion advances", routeDriveState.acceptFinished(chatNavigation))

rejects("stale tree hash") {
  try Data("{\"artifact\":\"macos-app\",\"treeHash\":\"stale\"}".utf8).write(to: shellStamp)
  _ = try ConsumerEvidenceTreeHashes.load(shellStamp: shellStamp, surfaceStamp: surfaceStamp)
}
try! Data("{\"artifact\":\"macos-app\",\"treeHash\":\"1111111111111111111111111111111111111111\"}".utf8).write(to: shellStamp)
rejects("wrong run") {
  _ = try ConsumerEvidenceCollector(resultURL: result, runId: "__launch-intent", shell: "macos", hashes: hashes)
}
rejects("wrong shell") {
  _ = try ConsumerEvidenceCollector(resultURL: result, runId: "run-ok", shell: "ios", hashes: hashes)
}
rejects("fixture supplied success") {
  _ = try RenderedConsumerObservation.decodeRenderedJSON(Data("{\"route\":\"chat\",\"state\":\"ready\",\"semantic\":\"intent\",\"fixture\":\"none\"}".utf8))
}
rejects("Listen without transcript") {
  _ = try RenderedConsumerObservation.decodeRenderedJSON(Data("{\"route\":\"listen\",\"state\":\"ready\",\"semantic\":\"listen\"}".utf8))
}
rejects("non-Listen transcript leakage") {
  _ = try RenderedConsumerObservation.decodeRenderedJSON(Data("{\"route\":\"chat\",\"state\":\"ready\",\"semantic\":\"chat\",\"transcript\":\"leak\"}".utf8))
}

try! Data("{\"runId\":\"prior-run\"}".utf8).write(to: result)
let collector = try! ConsumerEvidenceCollector(
  resultURL: result, runId: "run-macos-consumer", shell: "macos", hashes: hashes)
check("prior-run result removed", !FileManager.default.fileExists(atPath: result.path))
let memories = try! RenderedConsumerObservation.decodeRenderedJSON(
  Data("{\"route\":\"memories\",\"state\":\"ready\",\"semantic\":\"memories:rendered\"}".utf8))
let chat = try! RenderedConsumerObservation.decodeRenderedJSON(
  Data("{\"route\":\"chat\",\"state\":\"ready\",\"semantic\":\"chat:rendered\"}".utf8))
rejects("semantic from launch intent has wrong rendered route") {
  try collector.accept(chat, expected: .memories)
}
try! collector.accept(memories, expected: .memories)
rejects("duplicate route") { try collector.accept(memories, expected: .memories) }
rejects("missing routes") { try collector.finish() }
collector.teardown()
check("failure leaves no success", !FileManager.default.fileExists(atPath: result.path))

let complete = try! ConsumerEvidenceCollector(
  resultURL: result, runId: "run-macos-consumer", shell: "macos", hashes: hashes)
for route in ConsumerEvidenceRoute.allCases {
  let transcript = route == .listen ? ",\"transcript\":\"synthetic local transcript\"" : ""
  let json = "{\"route\":\"\(route.rawValue)\",\"state\":\"ready\",\"semantic\":\"\(route.rawValue):rendered\"\(transcript)}"
  try! complete.accept(
    try! RenderedConsumerObservation.decodeRenderedJSON(Data(json.utf8)), expected: route)
}
try! complete.finish()
let document = try! JSONSerialization.jsonObject(with: Data(contentsOf: result)) as! [String: Any]
check("exact document keys", Set(document.keys) == ["schema", "runId", "rows"])
check("exact schema", document["schema"] as? String == consumerEvidenceSchema)
let rows = document["rows"] as! [[String: Any]]
check("exact seven rows", rows.count == 7)
for row in rows {
  check("exact row keys", Set(row.keys) == ["runId", "shell", "domain", "fixture", "evidence", "observation", "shellTreeHash", "surfaceTreeHash"])
  check("row identity", row["runId"] as? String == "run-macos-consumer" && row["shell"] as? String == "macos")
  check("rendered evidence", row["fixture"] as? String == "none" && row["evidence"] as? String == "rendered-semantic")
  check("native tree hashes", row["shellTreeHash"] as? String == hashes.shell && row["surfaceTreeHash"] as? String == hashes.surface)
  let observation = row["observation"] as! [String: Any]
  let domain = row["domain"] as! String
  check("exact observation keys", Set(observation.keys) == (domain == "listen" ? ["route", "state", "semantic", "transcript"] : ["route", "state", "semantic"]))
}

exit(failed ? 1 : 0)
`;

test(
  "macOS native collector red-proofs identity, rendered semantics, route completeness, hashes, and atomic result reuse",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-macos-consumer-evidence-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", ["-o", binary, source, main], {
        env: { ...process.env, CLANG_MODULE_CACHE_PATH: join(scratch, "module-cache") },
      });
      const result = spawnSync(binary, [scratch], { encoding: "utf8" });
      assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
      for (const line of result.stdout.trim().split("\n")) assert.match(line, /^OK:/, result.stdout);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);

test("native evidence validator rejects reversed route rows and accepts canonical order", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-consumer-evidence-order-"));
  try {
    const result = join(scratch, "result.json");
    const domains = ["memories", "tasks", "conversations", "folders", "listen", "chat", "settings"];
    const document = {
      schema: "omi.consumer-evidence.v1",
      runId: "run-order-proof",
      rows: domains.map((domain) => ({
        runId: "run-order-proof",
        shell: "macos",
        domain,
        fixture: "none",
        evidence: "rendered-semantic",
        observation: {
          route: domain,
          state: "ready",
          semantic: `${domain}:rendered`,
          ...(domain === "listen" ? { transcript: "local transcript" } : {}),
        },
        shellTreeHash: "1".repeat(40),
        surfaceTreeHash: "2".repeat(40),
      })),
    };
    writeFileSync(result, JSON.stringify({ ...document, rows: [...document.rows].reverse() }));
    const reversed = spawnSync(process.execPath, [
      validator, "--file", result, "--run-id", "run-order-proof", "--shell", "macos",
    ], { encoding: "utf8" });
    assert.equal(reversed.status, 1);
    assert.match(reversed.stderr, /canonical domain order/);

    writeFileSync(result, JSON.stringify(document));
    const canonical = spawnSync(process.execPath, [
      validator, "--file", result, "--run-id", "run-order-proof", "--shell", "macos",
    ], { encoding: "utf8" });
    assert.equal(canonical.status, 0, canonical.stderr);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
