import XCTest

@testable import Omi_Computer

final class AgentProviderSetupTests: XCTestCase {

  private var tempHome: String = ""

  override func setUpWithError() throws {
    tempHome = NSTemporaryDirectory() + "omi-setup-tests-" + UUID().uuidString
    try FileManager.default.createDirectory(atPath: tempHome, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    try? FileManager.default.removeItem(atPath: tempHome)
  }

  private func installFakeExecutable(_ name: String) throws {
    // ~/.local/bin is first in the adapter search dirs for a fake home.
    let dir = tempHome + "/.local/bin"
    try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
    let path = dir + "/" + name
    try "#!/bin/sh\nexit 0\n".write(toFile: path, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path)
  }

  private func writeFile(_ relativePath: String) throws {
    let path = tempHome + "/" + relativePath
    try FileManager.default.createDirectory(
      atPath: (path as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
    try "{}".write(toFile: path, atomically: true, encoding: .utf8)
  }

  private var searchDirs: [String] { [tempHome + "/.local/bin"] }

  private func health(_ provider: AgentPillsManager.DirectedProvider) -> AgentProviderHealthReport {
    AgentProviderHealth.report(
      for: provider, environment: [:], fileManager: .default, homeDirectory: tempHome,
      searchDirectories: searchDirs)
  }

  private func plan(_ provider: AgentPillsManager.DirectedProvider) -> [AgentProviderInstaller.Step] {
    AgentProviderInstaller.plan(
      for: provider, health: health(provider), homeDirectory: tempHome,
      searchDirectories: searchDirs)
  }

  // MARK: - Health classification

  func testCodexMissingWhenNoBinary() {
    XCTAssertEqual(health(.codex).readiness, .missing)
  }

  func testCodexNeedsSetupWithoutBridge() throws {
    try installFakeExecutable("codex")
    let report = health(.codex)
    XCTAssertEqual(report.readiness, .needsSetup)
    XCTAssertTrue(report.detail.contains("codex-acp"))
  }

  func testCodexNeedsSetupWithoutAuth() throws {
    try installFakeExecutable("codex")
    try installFakeExecutable("codex-acp")
    let report = health(.codex)
    XCTAssertEqual(report.readiness, .needsSetup)
    XCTAssertTrue(report.detail.contains("signed in") || report.detail.contains("login"))
  }

  func testCodexReadyWithBinaryBridgeAndAuth() throws {
    try installFakeExecutable("codex")
    try installFakeExecutable("codex-acp")
    try writeFile(".codex/auth.json")
    XCTAssertEqual(health(.codex).readiness, .ready)
  }

  func testOpenClawNeedsSetupWithoutConfig() throws {
    try installFakeExecutable("openclaw")
    let report = health(.openclaw)
    XCTAssertEqual(report.readiness, .needsSetup)
    XCTAssertTrue(report.detail.contains("onboard"))
  }

  func testOpenClawReadyWithConfig() throws {
    try installFakeExecutable("openclaw")
    try writeFile(".openclaw/openclaw.json")
    XCTAssertEqual(health(.openclaw).readiness, .ready)
  }

  func testHermesMissingThenReady() throws {
    XCTAssertEqual(health(.hermes).readiness, .missing)
    try installFakeExecutable("hermes")
    XCTAssertEqual(health(.hermes).readiness, .ready)
  }

  func testCodexNotReadyWhenAuthPathIsDirectoryOrEmpty() throws {
    try installFakeExecutable("codex")
    try installFakeExecutable("codex-acp")
    // Directory at the auth path must not count as signed in.
    try FileManager.default.createDirectory(
      atPath: tempHome + "/.codex/auth.json", withIntermediateDirectories: true)
    XCTAssertEqual(health(.codex).readiness, .needsSetup)
    // Empty placeholder file must not count either.
    try FileManager.default.removeItem(atPath: tempHome + "/.codex/auth.json")
    FileManager.default.createFile(atPath: tempHome + "/.codex/auth.json", contents: Data())
    XCTAssertEqual(health(.codex).readiness, .needsSetup)
  }

  func testEnvOverrideForcesReady() {
    let report = AgentProviderHealth.report(
      for: .hermes,
      environment: ["OMI_HERMES_ADAPTER_COMMAND": "/somewhere/hermes acp"],
      fileManager: .default,
      homeDirectory: tempHome,
      searchDirectories: searchDirs)
    XCTAssertEqual(report.readiness, .ready)
  }

  // MARK: - Recipe planning

  func testCodexPlanFromScratchInstallsCliBridgeAndLogin() {
    let steps = plan(.codex)
    XCTAssertEqual(steps.map(\.title), ["Install Codex CLI", "Install codex-acp bridge", "Sign in to Codex"])
  }

  func testCodexPlanRepairsOnlyMissingBridge() throws {
    try installFakeExecutable("codex")
    try writeFile(".codex/auth.json")
    let steps = plan(.codex)
    XCTAssertEqual(steps.map(\.title), ["Install codex-acp bridge"])
  }

  func testHermesPlanInstallsThenConnectsPortal() {
    let steps = plan(.hermes)
    XCTAssertEqual(steps.map(\.title), ["Install Hermes agent", "Connect Hermes to Nous Portal"])
    XCTAssertTrue(steps[0].testDescription.contains("hermes-agent.nousresearch.com/install.sh"))
  }

  func testOpenClawPlanOnboardsWhenInstalledButUnconfigured() throws {
    try installFakeExecutable("openclaw")
    let steps = plan(.openclaw)
    XCTAssertEqual(steps.map(\.title), ["Onboard OpenClaw"])
  }

  private func writeFakeHermes(_ body: String) throws -> String {
    let path = tempHome + "/.local/bin/hermes"
    try FileManager.default.createDirectory(
      atPath: (path as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
    try "#!/bin/sh\n\(body)\n".write(toFile: path, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path)
    return path
  }

  func testHermesAuthProbeParsesLoggedInAndOut() throws {
    let loggedIn = try writeFakeHermes("echo 'nous: logged in'")
    XCTAssertTrue(AgentProviderInstaller.hermesNousAuthenticated(hermesPath: loggedIn))
    let loggedOut = try writeFakeHermes("echo 'nous: logged out'")
    XCTAssertFalse(AgentProviderInstaller.hermesNousAuthenticated(hermesPath: loggedOut))
  }

  func testHermesAuthProbeTerminatesHungBinary() throws {
    let hung = try writeFakeHermes("sleep 60")
    let start = Date()
    XCTAssertFalse(AgentProviderInstaller.hermesNousAuthenticated(hermesPath: hung, timeout: 1))
    XCTAssertLessThan(Date().timeIntervalSince(start), 10)
  }

  func testHermesAuthProbeMissingBinaryIsFalse() {
    XCTAssertFalse(AgentProviderInstaller.hermesNousAuthenticated(hermesPath: tempHome + "/nope"))
  }

  func testReadyProviderPlansNoSteps() throws {
    try installFakeExecutable("hermes")
    let steps = plan(.hermes)
    XCTAssertTrue(steps.isEmpty)
  }
}
