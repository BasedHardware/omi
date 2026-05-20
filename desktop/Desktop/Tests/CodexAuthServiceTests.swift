import XCTest

@testable import Omi_Computer

final class CodexAuthServiceTests: XCTestCase {

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: "codex_auth_enrolled")
    UserDefaults.standard.removeObject(forKey: "codex_preferred_model")
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: "codex_auth_enrolled")
    UserDefaults.standard.removeObject(forKey: "codex_preferred_model")
    super.tearDown()
  }

  func testEnrollmentFingerprintIsStableHex() {
    let fp = CodexAuthService.enrollmentFingerprint(for: "account-123")
    XCTAssertEqual(fp.count, 64)
    XCTAssertTrue(fp.allSatisfy { $0.isHexDigit })
    XCTAssertEqual(fp, CodexAuthService.enrollmentFingerprint(for: "account-123"))
  }

  func testIsActiveRequiresEnrollmentAndSnapshot() {
    let tempAuth = makeTempCodexHomeWithoutAuth()
    defer { tempAuth.cleanup() }

    XCTAssertFalse(CodexAuthService.isActive)
    CodexAuthService.markEnrolled()
    XCTAssertFalse(CodexAuthService.isActive)
  }

  func testLoadSnapshotParsesNestedTokensFormat() throws {
    let dir = FileManager.default.temporaryDirectory
      .appendingPathComponent("codex-auth-test-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }

    let authURL = dir.appendingPathComponent("auth.json")
    let payload = """
      {
        "auth_mode": "chatgpt",
        "tokens": {
          "access_token": "test-access",
          "refresh_token": "test-refresh",
          "account_id": "acct-nested"
        }
      }
      """
    try payload.write(to: authURL, atomically: true, encoding: .utf8)

    let previous = ProcessInfo.processInfo.environment["CODEX_HOME"]
    setenv("CODEX_HOME", dir.path, 1)
    defer {
      if let previous {
        setenv("CODEX_HOME", previous, 1)
      } else {
        unsetenv("CODEX_HOME")
      }
    }

    let snap = CodexAuthService.loadSnapshot()
    XCTAssertEqual(snap?.accessToken, "test-access")
    XCTAssertEqual(snap?.accountId, "acct-nested")
    XCTAssertEqual(snap?.refreshToken, "test-refresh")
  }

  func testMemorySearchModeDefaultsToWikiWhenCodexEnrolled() {
    CodexAuthService.markEnrolled()
    XCTAssertEqual(MemorySearchMode.current, .localWiki)
  }
}

final class CodexLLMClientTests: XCTestCase {

  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: "codex_auth_enrolled")
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: "codex_auth_enrolled")
    super.tearDown()
  }

  func testProviderConfigRequiresEnrollmentAndAuthFile() throws {
    let tempAuth = makeTempCodexHomeWithoutAuth()
    defer { tempAuth.cleanup() }

    XCTAssertNil(CodexLLMClient.providerConfig())
    CodexAuthService.markEnrolled()
    XCTAssertNil(CodexLLMClient.providerConfig())
  }
}

private struct TempCodexHome {
  let path: String
  let previous: String?

  func cleanup() {
    if let previous {
      setenv("CODEX_HOME", previous, 1)
    } else {
      unsetenv("CODEX_HOME")
    }
    try? FileManager.default.removeItem(atPath: path)
  }
}

private func makeTempCodexHomeWithoutAuth() -> TempCodexHome {
  let dir = FileManager.default.temporaryDirectory
    .appendingPathComponent("codex-auth-empty-\(UUID().uuidString)")
  try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
  let previous = ProcessInfo.processInfo.environment["CODEX_HOME"]
  setenv("CODEX_HOME", dir.path, 1)
  return TempCodexHome(path: dir.path, previous: previous)
}
