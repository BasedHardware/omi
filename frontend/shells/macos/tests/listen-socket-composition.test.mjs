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

let base = URL(string: "https://staging.example.test/api")!
let authority = ShellTransportAuthority(baseURL: base, token: "shell-token")
let decision = authority.prepareListen(id: "listen-1", path: "/v4/listen?language=en")
if case let .dispatch(prepared) = decision {
  print("URL=\(prepared.request.url!.absoluteString)")
  let auth = prepared.request.value(forHTTPHeaderField: "Authorization") ?? "missing"
  print("AUTH=\(auth)")
  exit(0)
}
print("FAIL")
exit(1)
`;

test(
  "macOS production socket composition targets the API authority with the shell bearer",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-listen-socket-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(root, "shell/Sources/OmiShell/BridgeHttpContract.generated.swift"),
        join(root, "shell/Sources/OmiShell/BridgeHttp.swift"),
        join(root, "shell/Sources/OmiShell/ListenSocket.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "WebKit",
      ]);
      const output = execFileSync(binary, { encoding: "utf8" });
      assert.equal(output, "URL=wss://staging.example.test/v4/listen?language=en\nAUTH=Bearer shell-token\n");
      assert.equal(output.includes("127.0.0.1:5290"), false);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
