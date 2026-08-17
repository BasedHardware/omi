// Behavioral (not just source-scraped) proof that a page cannot forge or
// suppress the per-run `x-omi-client-id` header, and that an absent
// OMI_RUN_CLIENT_ID sends no header at all rather than a fabricated one.
//
// This compiles BridgeHttp.swift + the generated contract together with a
// small standalone harness and runs the real BridgeHttpPolicy.prepare seam —
// the same seam BridgeHttpHandler and the generated host-conformance runner
// both call — so the assertions exercise production behavior through a
// controllable seam, not a remembered description of it (AGENTS.md rule 14:
// row-count/string-presence checks are the decorative shape; this is not
// that).
//
// Requires the Xcode/Swift toolchain (`swiftc`) that scripts/build-shell.sh
// itself requires. Skips cleanly where it is unavailable rather than failing
// a non-macOS or toolchain-less lane.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcesDir = join(root, "shell/Sources/OmiShell");

function hasSwiftc() {
  try {
    execFileSync("swiftc", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

// The harness file MUST be named exactly `main.swift`: swiftc only allows
// top-level executable statements in a file with that literal name when
// compiling multiple files together.
const HARNESS_MAIN = `
import Foundation

var exitCode: Int32 = 0
func check(_ name: String, _ cond: Bool) {
  print(cond ? "OK: \\(name)" : "FAIL: \\(name)")
  if !cond { exitCode = 1 }
}

let base = URL(string: "https://api.example")!

// A page-forged copy of the header, any casing, must not survive — the real
// clientId always wins.
do {
  let decision = BridgeHttpPolicy.prepare(
    id: "t1", method: "GET", path: "/v1/tasks",
    headers: [
      "X-Omi-Client-Id": "forged-by-page",
      "X-Omi-Contract-Version": "999.0.0",
    ], body: nil,
    baseURL: base, token: "tok", clientId: "real-run-id")
  if case let .dispatch(prepared) = decision {
    check("forged-header-overridden", prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == "real-run-id::macos")
    check("forged-contract-overridden", prepared.request.value(forHTTPHeaderField: "x-omi-contract-version") == "1.0.0")
  } else {
    check("t1-dispatch", false)
  }
}

// Absent run id sends no header at all — never a fabricated value.
do {
  let decision = BridgeHttpPolicy.prepare(
    id: "t2", method: "GET", path: "/v1/tasks",
    headers: [:], body: nil,
    baseURL: base, token: "tok", clientId: nil)
  if case let .dispatch(prepared) = decision {
    check("absent-clientid-sends-no-header", prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == nil)
  } else {
    check("t2-dispatch", false)
  }
}

// A present run id is combined with the fixed native shell identity.
do {
  let decision = BridgeHttpPolicy.prepare(
    id: "t3", method: "GET", path: "/v1/tasks",
    headers: [:], body: nil,
    baseURL: base, token: "tok", clientId: "run-42")
  if case let .dispatch(prepared) = decision {
    check("present-run-composes-macos-identity", prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == "run-42::macos")
  } else {
    check("t3-dispatch", false)
  }
}

// A page trying to SUPPRESS the header with an empty-string copy still gets
// the real id — suppression must not work either.
do {
  let decision = BridgeHttpPolicy.prepare(
    id: "t4", method: "GET", path: "/v1/tasks",
    headers: ["x-omi-client-id": ""], body: nil,
    baseURL: base, token: "tok", clientId: "real-run-id")
  if case let .dispatch(prepared) = decision {
    check("suppression-attempt-overridden", prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == "real-run-id::macos")
  } else {
    check("t4-dispatch", false)
  }
}

// Chat generation cancellation remains the authenticated generic DELETE, but
// P7 producer attribution and contract version are still host-injected.
do {
  let decision = BridgeHttpPolicy.prepare(
    id: "t5", method: "DELETE", path: "/v1/chat-generations/generation-opaque-01",
    headers: ["x-omi-client-id": "forged", "x-omi-contract-version": "forged"],
    body: nil, baseURL: base, token: "tok", clientId: "run-cancel")
  if case let .dispatch(prepared) = decision {
    check("chat-cancel-has-exact-host-identity", prepared.request.httpMethod == "DELETE"
      && prepared.request.url?.path == "/v1/chat-generations/generation-opaque-01"
      && prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == "run-cancel::macos"
      && prepared.request.value(forHTTPHeaderField: "x-omi-contract-version") == "1.0.0")
  } else {
    check("t5-dispatch", false)
  }
}

exit(exitCode)
`;

test(
  "a page can neither forge nor suppress the per-run x-omi-client-id header (compiled behavioral check)",
  { skip: hasSwiftc() ? false : "swiftc not available in this environment" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-bridge-http-clientid-"));
    try {
      const harnessMain = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(harnessMain, HARNESS_MAIN);
      execFileSync(
        "swiftc",
        [
          "-o", binary,
          join(sourcesDir, "BridgeHttp.swift"),
          join(sourcesDir, "BridgeHttpContract.generated.swift"),
          harnessMain,
          "-framework", "Foundation",
          "-framework", "WebKit",
        ],
        { stdio: "pipe" },
      );
      assert.ok(existsSync(binary), "harness binary was not produced");
      const output = execFileSync(binary, { encoding: "utf8" });
      // Every line must read OK — any FAIL line, or a nonzero exit (checked
      // implicitly: execFileSync throws on nonzero exit), is a real failure.
      const lines = output.trim().split("\n");
      assert.ok(lines.length === 6, `expected 6 check lines, got: ${output}`);
      for (const line of lines) {
        assert.ok(line.startsWith("OK:"), `expected OK, got: ${line}`);
      }
      // red-proof: removing the `shellClientId(runId:)` injection block from
      // BridgeHttpPolicy.prepare in BridgeHttp.swift (so the shell's real
      // client id is never attached) deterministically fails
      // "present-run-composes-macos-identity", "suppression-attempt-overridden",
      // "forged-header-overridden", and the Chat cancellation identity check.
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
