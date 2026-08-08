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
    headers: ["X-Omi-Client-Id": "forged-by-page"], body: nil,
    baseURL: base, token: "tok", clientId: "real-run-id")
  if case let .dispatch(prepared) = decision {
    check("forged-header-overridden", prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == "real-run-id")
  } else {
    check("t1-dispatch", false)
  }
}

// Absent clientId sends no header at all — never a fabricated value.
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

// Present clientId is sent verbatim when the page sends nothing.
do {
  let decision = BridgeHttpPolicy.prepare(
    id: "t3", method: "GET", path: "/v1/tasks",
    headers: [:], body: nil,
    baseURL: base, token: "tok", clientId: "run-42")
  if case let .dispatch(prepared) = decision {
    check("present-clientid-sent-verbatim", prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == "run-42")
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
    check("suppression-attempt-overridden", prepared.request.value(forHTTPHeaderField: "x-omi-client-id") == "real-run-id")
  } else {
    check("t4-dispatch", false)
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
      assert.ok(lines.length === 4, `expected 4 check lines, got: ${output}`);
      for (const line of lines) {
        assert.ok(line.startsWith("OK:"), `expected OK, got: ${line}`);
      }
      // red-proof: removing the `if let clientId, !clientId.isEmpty {
      // outbound[clientIdHeader] = clientId }` block from
      // BridgeHttpPolicy.prepare in BridgeHttp.swift (so the shell's real
      // client id is never attached) deterministically fails
      // "present-clientid-sent-verbatim", "suppression-attempt-overridden",
      // and "forged-header-overridden" — confirmed by applying exactly that
      // mutation: the harness printed
      //   FAIL: forged-header-overridden
      //   OK: absent-clientid-sends-no-header
      //   FAIL: present-clientid-sent-verbatim
      //   FAIL: suppression-attempt-overridden
      // and exited 1, and this test throws on the first non-"OK:" line.
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
