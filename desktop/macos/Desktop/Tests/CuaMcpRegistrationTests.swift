import XCTest

@testable import Omi_Computer

/// Turning the switch on has to leave two artefacts behind, or the tools exist
/// and nothing can reach them: the entry Omi's own runtime reads, and the shim a
/// stdio-only client launches.
final class CuaMcpRegistrationTests: XCTestCase {
  private var tempRoot = FileManager.default.temporaryDirectory

  override func setUpWithError() throws {
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-cua-test-\(UUID().uuidString)")
    LocalSkillsStore.rootURLOverride = tempRoot
  }

  override func tearDownWithError() throws {
    LocalSkillsStore.rootURLOverride = nil
    try? FileManager.default.removeItem(at: tempRoot)
  }

  func testRegisteringWritesTheServerEntryAndTheShim() throws {
    try CuaMcpRegistration.register(token: "tok-123")

    let entry = LocalMcpStore.readAllServers()["omi-computer-use"] as? [String: Any]
    XCTAssertEqual(entry?["url"] as? String, CuaMcpRegistration.endpointURL)
    XCTAssertEqual(entry?["token"] as? String, "tok-123")
    XCTAssertTrue(CuaMcpRegistration.isRegistered(token: "tok-123"))

    let script = try String(contentsOf: CuaStdioShim.scriptURL, encoding: .utf8)
    XCTAssertTrue(script.hasPrefix("#!/bin/sh"))
    XCTAssertTrue(script.contains(CuaMcpRegistration.endpointURL))
    XCTAssertTrue(script.contains("Bearer tok-123"))
    let permissions =
      try FileManager.default.attributesOfItem(
        atPath: CuaStdioShim.scriptURL.path)[.posixPermissions] as? NSNumber
    XCTAssertEqual(permissions?.int16Value, 0o700)
  }

  /// A rotated token leaves an entry that answers 401 to every call, which a
  /// client shows as a server with no tools rather than as an auth failure.
  func testAStaleTokenReadsAsUnregistered() throws {
    try CuaMcpRegistration.register(token: "old")
    XCTAssertFalse(CuaMcpRegistration.isRegistered(token: "new"))
  }

  func testUnregisteringRemovesBoth() throws {
    try CuaMcpRegistration.register(token: "tok-123")
    CuaMcpRegistration.unregister()

    XCTAssertNil(LocalMcpStore.readAllServers()["omi-computer-use"])
    XCTAssertFalse(FileManager.default.fileExists(atPath: CuaStdioShim.scriptURL.path))
  }

  /// Hand-edited entries in the same file must survive, the way every other
  /// write to mcp.json does.
  func testOtherServersAreLeftAlone() throws {
    try LocalMcpStore.addCommandServer(name: "playwright", commandLine: "npx @playwright/mcp@latest")
    try CuaMcpRegistration.register(token: "tok-123")
    CuaMcpRegistration.unregister()

    XCTAssertEqual(LocalMcpStore.listServers().map(\.name), ["playwright"])
  }
}
