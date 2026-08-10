import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sources = join(root, "shell/Sources/OmiShell");

function hasSwiftc() {
  try { execFileSync("swiftc", ["--version"], { stdio: "ignore" }); return true; }
  catch { return false; }
}

const HARNESS = String.raw`
import Foundation

final class FakeCredentialStore: CredentialStore, @unchecked Sendable {
  var deleted: [String] = []
  var logDescription: String { "fake" }
  func read(account: String) throws -> String? { nil }
  func write(account: String, token: String) throws {}
  func delete(account: String) throws { deleted.append(account) }
}

var failed = false
func check(_ name: String, _ condition: Bool) {
  print(condition ? "OK: \(name)" : "FAIL: \(name)")
  if !condition { failed = true }
}

let base = URL(string: "https://settings.example.test:8443")!
let keychain = FakeCredentialStore()
let custody = BridgeHttpCredentialCustody(token: "environment-token") {
  try? SessionBootstrap.deleteCredential(for: base, from: keychain)
}

func prepare(_ id: String = "read") -> BridgeHttpPolicyDecision {
  custody.prepare(
    id: id, method: "GET", path: "/v1/settings", headers: [:], body: nil,
    baseURL: base, clientId: nil)
}

if case .dispatch = prepare("before") { check("credential-used-before-signout", true) }
else { check("credential-used-before-signout", false) }

custody.observe(method: "DELETE", path: "/v1/session/current", status: 503)
if case .dispatch = prepare("after-failed") { check("failed-delete-keeps-token", true) }
else { check("failed-delete-keeps-token", false) }

for (method, path, status) in [
  ("GET", "/v1/session/current", 204),
  ("DELETE", "/v1/session/current?all=true", 204),
  ("DELETE", "/v1/session/other", 204),
  ("DELETE", "/v1/session/current", 200),
] {
  custody.observe(method: method, path: path, status: status)
}
if case .dispatch = prepare("after-near-misses") { check("near-misses-keep-token", true) }
else { check("near-misses-keep-token", false) }

custody.observe(method: "DELETE", path: "/v1/session/current", status: 204)
if case let .failure(reason, _) = prepare("after-success") {
  check("next-settings-read-is-credential-free", reason == .notAuthenticated)
} else {
  check("next-settings-read-is-credential-free", false)
}
check("origin-scoped-keychain-item-deleted", keychain.deleted == ["api@https://settings.example.test:8443"])

exit(failed ? 1 : 0)
`;

test(
  "macOS clears live and origin-scoped Keychain custody only after exact successful sign-out",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-settings-signout-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(sources, "BridgeHttpContract.generated.swift"),
        join(sources, "BridgeHttp.swift"),
        join(sources, "Credentials.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "WebKit",
        "-framework", "Security",
        "-framework", "LocalAuthentication",
      ], {
        env: { ...process.env, CLANG_MODULE_CACHE_PATH: join(scratch, "module-cache") },
      });
      const output = execFileSync(binary, { encoding: "utf8" });
      for (const line of output.trim().split("\n")) {
        assert.match(line, /^OK:/, output);
      }
      // red-proof: remove the live custody observe call, widen any exact
      // method/path/status predicate, or remove SessionBootstrap's scoped
      // deletion and the named behavioral check above fails.
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
