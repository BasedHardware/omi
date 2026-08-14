import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
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

enum FakeDeleteError: Error { case refused }

final class FakeCredentialStore: CredentialStore, @unchecked Sendable {
  var deleted: [String] = []
  var deleteFails = false
  var logDescription: String { "fake" }
  func read(account: String) throws -> String? { nil }
  func write(account: String, token: String) throws {}
  func delete(account: String) throws {
    if deleteFails { throw FakeDeleteError.refused }
    deleted.append(account)
  }
}

var failed = false
func check(_ name: String, _ condition: Bool) {
  print(condition ? "OK: \(name)" : "FAIL: \(name)")
  if !condition { failed = true }
}

MainActor.assumeIsolated {
let base = URL(string: "https://settings.example.test:8443")!
let keychain = FakeCredentialStore()
var deleteFailureLogs = 0
let authority = ShellTransportAuthority(
  baseURL: base, token: "environment-token",
  onSuccessfulSignOut: {
    do {
      try SessionBootstrap.deleteCredential(for: base, from: keychain)
    } catch {
      deleteFailureLogs += 1
    }
  })
let http = authority.makeHTTPHandler(clientId: nil)
let listen = authority.makeListenHandler()

@MainActor func prepareHTTP(_ id: String = "read") -> BridgeHttpPolicyDecision {
  http.prepareUsingCurrentCustodyForConformance(id)
}

func prepareListen(_ id: String = "listen") -> ListenSocketPolicyDecision {
  listen.prepareUsingCurrentCustodyForConformance(id: id, path: "/v4/listen")
}

if case .dispatch = prepareHTTP("http-before") { check("http-used-before-signout", true) }
else { check("http-used-before-signout", false) }
if case .dispatch = prepareListen("listen-before") { check("listen-used-before-signout", true) }
else { check("listen-used-before-signout", false) }

http.observeResponseForConformance(method: "DELETE", path: "/v1/session/current", status: 503)
if case .dispatch = prepareHTTP("http-after-status") { check("near-miss-status-keeps-http", true) }
else { check("near-miss-status-keeps-http", false) }
if case .dispatch = prepareListen("listen-after-status") { check("near-miss-status-keeps-listen", true) }
else { check("near-miss-status-keeps-listen", false) }

http.observeResponseForConformance(method: "DELETE", path: "/v1/session/other", status: 204)
if case .dispatch = prepareHTTP("http-after-route") { check("near-miss-route-keeps-http", true) }
else { check("near-miss-route-keeps-http", false) }
if case .dispatch = prepareListen("listen-after-route") { check("near-miss-route-keeps-listen", true) }
else { check("near-miss-route-keeps-listen", false) }

let timeout = BridgeHttpPolicy.transportFailure(id: "timeout", name: "timeout")
check("timeout-classified-without-clearing", timeout.reason == .timeout)
if case .dispatch = prepareHTTP("http-after-timeout") { check("timeout-keeps-http", true) }
else { check("timeout-keeps-http", false) }
if case .dispatch = prepareListen("listen-after-timeout") { check("timeout-keeps-listen", true) }
else { check("timeout-keeps-listen", false) }

http.observeResponseForConformance(method: "DELETE", path: "/v1/session/current", status: 204)
if case let .failure(reason, _) = prepareHTTP("http-after-success") {
  check("next-http-request-is-credential-free", reason == .notAuthenticated)
} else {
  check("next-http-request-is-credential-free", false)
}
if case .failure = prepareListen("listen-after-success") {
  check("next-listen-open-is-credential-free", true)
} else {
  check("next-listen-open-is-credential-free", false)
}
check("origin-scoped-keychain-item-deleted", keychain.deleted == ["api@https://settings.example.test:8443"])

let failingKeychain = FakeCredentialStore()
failingKeychain.deleteFails = true
let failingAuthority = ShellTransportAuthority(
  baseURL: base, token: "second-environment-token",
  onSuccessfulSignOut: {
    do {
      try SessionBootstrap.deleteCredential(for: base, from: failingKeychain)
    } catch {
      deleteFailureLogs += 1
    }
  })
let failingHTTP = failingAuthority.makeHTTPHandler(clientId: nil)
let failingListen = failingAuthority.makeListenHandler()
failingHTTP.observeResponseForConformance(
  method: "DELETE", path: "/v1/session/current", status: 204)
if case let .failure(reason, _) = failingHTTP.prepareUsingCurrentCustodyForConformance("http-after-delete-error") {
  check("keychain-failure-cannot-resurrect-http", reason == .notAuthenticated)
} else {
  check("keychain-failure-cannot-resurrect-http", false)
}
if case .failure = failingListen.prepareUsingCurrentCustodyForConformance(
  id: "listen-after-delete-error", path: "/v4/listen")
{
  check("keychain-failure-cannot-resurrect-listen", true)
} else {
  check("keychain-failure-cannot-resurrect-listen", false)
}
check("keychain-deletion-failure-logged", deleteFailureLogs == 1)

exit(failed ? 1 : 0)
}
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
        join(sources, "ListenSocket.swift"),
        join(sources, "Credentials.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "WebKit",
        "-framework", "Security",
        "-framework", "LocalAuthentication",
      ], {
        env: { ...process.env, CLANG_MODULE_CACHE_PATH: join(scratch, "module-cache") },
      });
      const result = spawnSync(binary, { encoding: "utf8" });
      assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
      const output = result.stdout;
      for (const line of output.trim().split("\n")) {
        assert.match(line, /^OK:/, output);
      }
      // red-proof: make either handler retain a copied token, remove the live
      // custody observe call, widen its exact predicate, or remove the scoped
      // deletion and a named cross-transport/near-miss assertion fails.
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
