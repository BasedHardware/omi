import XCTest

@testable import Omi_Computer

/// Covers the Hermes → Nous device-code connect flow: auth-signal probing,
/// installed-but-signed-out routing, CLI stdout parsing, and prompt copy.
final class HermesConnectFlowTests: XCTestCase {

  // MARK: - Helpers

  private func makeTempHome(withHermesExecutable: Bool = true) throws -> URL {
    let home = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-hermes-connect-\(UUID().uuidString)", isDirectory: true)
    if withHermesExecutable {
      let bin = home.appendingPathComponent(".local/bin", isDirectory: true)
      try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
      let executable = bin.appendingPathComponent("hermes")
      try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
      try FileManager.default.setAttributes(
        [.posixPermissions: 0o755], ofItemAtPath: executable.path)
    } else {
      try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
    }
    return home
  }

  private func writeHermesFile(_ home: URL, name: String, contents: String) throws {
    let hermesDir = home.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: hermesDir, withIntermediateDirectories: true)
    try contents.write(
      to: hermesDir.appendingPathComponent(name), atomically: true, encoding: .utf8)
  }

  // MARK: - HermesAuthProbe

  func testProbeFindsNoCredentialsInEmptyHome() throws {
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }

    XCTAssertFalse(
      HermesAuthProbe.hasAnyInferenceCredential(environment: [:], homeDirectory: home.path))
    XCTAssertFalse(
      HermesAuthProbe.isNousAuthenticated(environment: [:], homeDirectory: home.path))
  }

  func testProbeDetectsNousRefreshToken() throws {
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }
    try writeHermesFile(
      home, name: "auth.json",
      contents: #"{"providers": {"nous": {"access_token": "jwt", "refresh_token": "rt-1"}}}"#)

    XCTAssertTrue(
      HermesAuthProbe.hasAnyInferenceCredential(environment: [:], homeDirectory: home.path))
    XCTAssertTrue(
      HermesAuthProbe.isNousAuthenticated(environment: [:], homeDirectory: home.path))
  }

  func testProbeTreatsQuarantinedNousStateAsSignedOut() throws {
    // Hermes strips token fields on quarantine but keeps routing metadata.
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }
    try writeHermesFile(
      home, name: "auth.json",
      contents: #"{"providers": {"nous": {"portal_base_url": "https://portal.nousresearch.com", "last_auth_error": {"code": "invalid_grant"}}}}"#)

    XCTAssertFalse(
      HermesAuthProbe.hasAnyInferenceCredential(environment: [:], homeDirectory: home.path))
    XCTAssertFalse(
      HermesAuthProbe.isNousAuthenticated(environment: [:], homeDirectory: home.path))
  }

  func testProbeDetectsOtherProviderCredentials() throws {
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }
    try writeHermesFile(
      home, name: "auth.json",
      contents: #"{"credential_pool": {"openrouter": [{"auth_type": "api_key"}]}}"#)

    XCTAssertTrue(
      HermesAuthProbe.hasAnyInferenceCredential(environment: [:], homeDirectory: home.path))
    XCTAssertFalse(
      HermesAuthProbe.isNousAuthenticated(environment: [:], homeDirectory: home.path))
  }

  func testProbeDetectsEnvFileAPIKeyButIgnoresCommentsAndBlanks() throws {
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }
    try writeHermesFile(
      home, name: ".env",
      contents: """
      # OPENROUTER_API_KEY=commented-out
      EMPTY_API_KEY=
      SOME_SETTING=on
      """)
    XCTAssertFalse(
      HermesAuthProbe.hasAnyInferenceCredential(environment: [:], homeDirectory: home.path))

    try writeHermesFile(
      home, name: ".env",
      contents: "OPENROUTER_API_KEY=sk-or-live\n")
    XCTAssertTrue(
      HermesAuthProbe.hasAnyInferenceCredential(environment: [:], homeDirectory: home.path))
  }

  func testProbeDetectsProcessEnvironmentKey() {
    XCTAssertTrue(
      HermesAuthProbe.hasAnyInferenceCredential(
        environment: ["ANTHROPIC_API_KEY": "sk-ant-1"],
        homeDirectory: "/tmp/missing-home-\(UUID().uuidString)"))
  }

  func testProbeHonorsHermesHomeOverride() throws {
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }
    let customHermesHome = home.appendingPathComponent("custom-hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: customHermesHome, withIntermediateDirectories: true)
    try #"{"providers": {"nous": {"refresh_token": "rt-2"}}}"#.write(
      to: customHermesHome.appendingPathComponent("auth.json"), atomically: true, encoding: .utf8)

    XCTAssertTrue(
      HermesAuthProbe.isNousAuthenticated(
        environment: ["HERMES_HOME": customHermesHome.path],
        homeDirectory: "/tmp/missing-home"))
  }

  // MARK: - Detector routing

  func testDetectorRoutesInstalledButSignedOutHermesToAuthentication() throws {
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }

    let availability = LocalAgentProviderDetector.availability(
      for: .hermes,
      environment: [:],
      homeDirectory: home.path)

    XCTAssertFalse(availability.isAvailable)
    XCTAssertTrue(availability.needsAuthentication)
    XCTAssertEqual(
      availability.setupPrompt,
      "Hermes is installed but isn't signed in yet. I can open the Nous sign-in page in your browser to connect it.")
  }

  func testDetectorKeepsAuthenticatedHermesAvailable() throws {
    let home = try makeTempHome()
    defer { try? FileManager.default.removeItem(at: home) }
    try writeHermesFile(
      home, name: "auth.json",
      contents: #"{"providers": {"nous": {"refresh_token": "rt-3"}}}"#)

    let availability = LocalAgentProviderDetector.availability(
      for: .hermes,
      environment: [:],
      homeDirectory: home.path)

    XCTAssertTrue(availability.isAvailable)
  }

  func testDetectorMissingHermesStillReportsMissing() {
    let availability = LocalAgentProviderDetector.availability(
      for: .hermes,
      environment: ["PATH": "/tmp/definitely-missing-\(UUID().uuidString)"],
      homeDirectory: "/tmp/missing-home")

    XCTAssertEqual(availability.status, .missing)
    XCTAssertFalse(availability.needsAuthentication)
  }

  func testDetectorAuthCheckSkipsProvidersWithoutSetupProbe() throws {
    // Codex has no auth/onboard probe: a found executable is simply available.
    let home = try makeTempHome(withHermesExecutable: false)
    defer { try? FileManager.default.removeItem(at: home) }
    let bin = home.appendingPathComponent(".local/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    let executable = bin.appendingPathComponent("codex")
    try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: 0o755], ofItemAtPath: executable.path)

    let availability = LocalAgentProviderDetector.availability(
      for: .codex,
      environment: [:],
      homeDirectory: home.path)

    XCTAssertTrue(availability.isAvailable)
  }

  func testDetectorTreatsUnonboardedOpenClawAsNeedsAuth() throws {
    // OpenClaw installs the binary with `--no-onboard`; a present binary with
    // no config is "installed but not set up", not "available".
    let home = try makeTempHome(withHermesExecutable: false)
    defer { try? FileManager.default.removeItem(at: home) }
    let bin = home.appendingPathComponent(".local/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    let executable = bin.appendingPathComponent("openclaw")
    try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes(
      [.posixPermissions: 0o755], ofItemAtPath: executable.path)

    let notOnboarded = LocalAgentProviderDetector.availability(
      for: .openclaw, environment: [:], homeDirectory: home.path)
    XCTAssertTrue(notOnboarded.needsAuthentication)
    XCTAssertFalse(notOnboarded.isAvailable)

    // Once onboarded (config with Gateway + default model), it is available.
    let openClawDir = home.appendingPathComponent(".openclaw", isDirectory: true)
    try FileManager.default.createDirectory(at: openClawDir, withIntermediateDirectories: true)
    try """
    {"gateway":{"port":18789},"agents":{"defaults":{"model":{"primary":"anthropic/claude-opus-4-8"}}}}
    """.write(to: openClawDir.appendingPathComponent("openclaw.json"), atomically: true, encoding: .utf8)

    let onboarded = LocalAgentProviderDetector.availability(
      for: .openclaw, environment: [:], homeDirectory: home.path)
    XCTAssertTrue(onboarded.isAvailable)
  }

  // MARK: - Device-code stdout parsing

  func testParserExtractsVerificationURLAndUserCode() {
    var parser = HermesDeviceCodeOutputParser()
    for line in [
      "Starting Hermes login via Nous Portal...",
      "Portal: https://portal.nousresearch.com",
      "",
      "To continue:",
      "  1. Open: https://portal.nousresearch.com/activate?user_code=ABCD-EFGH",
      "  2. If prompted, enter code: ABCD-EFGH",
      "Waiting for approval (polling every 5s)...",
    ] {
      parser.consume(line: line)
    }

    XCTAssertEqual(
      parser.verificationURL?.absoluteString,
      "https://portal.nousresearch.com/activate?user_code=ABCD-EFGH")
    XCTAssertEqual(parser.userCode, "ABCD-EFGH")
  }

  func testParserHandlesMissingUserCodeLine() {
    var parser = HermesDeviceCodeOutputParser()
    parser.consume(line: "  1. Open: https://portal.nousresearch.com/activate")

    XCTAssertEqual(parser.verificationURL?.absoluteString, "https://portal.nousresearch.com/activate")
    XCTAssertNil(parser.userCode)
  }

  func testParserIgnoresNonURLOpenLines() {
    var parser = HermesDeviceCodeOutputParser()
    parser.consume(line: "  1. Open: not a url")
    XCTAssertNil(parser.verificationURL)
  }

  func testParserKeepsFirstURLAndCode() {
    var parser = HermesDeviceCodeOutputParser()
    parser.consume(line: "1. Open: https://portal.nousresearch.com/activate?user_code=AAAA")
    parser.consume(line: "1. Open: https://evil.example.com/second")
    parser.consume(line: "2. If prompted, enter code: AAAA")
    parser.consume(line: "2. If prompted, enter code: BBBB")

    XCTAssertEqual(
      parser.verificationURL?.absoluteString,
      "https://portal.nousresearch.com/activate?user_code=AAAA")
    XCTAssertEqual(parser.userCode, "AAAA")
  }

  // MARK: - Authentication plan + prompt copy

  func testHermesAuthenticationPlanIsAuthenticateKind() {
    let plan = AgentPillsManager.DirectedProvider.hermes.authenticationPlan
    XCTAssertEqual(plan.kind, .authenticate)
    XCTAssertNil(plan.installCommand)
    XCTAssertEqual(
      plan.documentationURL.absoluteString,
      "https://hermes-agent.nousresearch.com/docs/integrations/nous-portal")
  }

  func testInstallPlansStayInstallKind() {
    XCTAssertEqual(AgentPillsManager.DirectedProvider.hermes.installPlan.kind, .install)
    // OpenClaw's installer is still an install plan, but it now has a distinct
    // authenticate plan for the post-install onboarding step.
    XCTAssertEqual(AgentPillsManager.DirectedProvider.openclaw.installPlan.kind, .install)
    XCTAssertEqual(AgentPillsManager.DirectedProvider.openclaw.authenticationPlan.kind, .authenticate)
    XCTAssertNil(AgentPillsManager.DirectedProvider.openclaw.authenticationPlan.installCommand)
  }

  func testOpenClawAuthenticatePromptCopyIsNotBrowserFlow() {
    let plan = AgentPillsManager.DirectedProvider.openclaw.authenticationPlan
    let state = AgentInstallPromptState(plan: plan)
    // Must not claim a browser sign-in — OpenClaw onboards non-interactively.
    XCTAssertFalse(state.detailText.lowercased().contains("browser"))
    XCTAssertTrue(state.detailText.contains("OpenClaw"))
    XCTAssertEqual(state.primaryActionTitle, "Connect OpenClaw")
  }

  func testPromptCopyForAuthenticateFlow() {
    let plan = AgentPillsManager.DirectedProvider.hermes.authenticationPlan
    var state = AgentInstallPromptState(plan: plan)

    XCTAssertEqual(
      state.detailText,
      "Omi will open the sign-in page in your browser, then wait for your approval.")
    XCTAssertEqual(state.primaryActionTitle, "Connect Hermes")

    state.status = .waitingForApproval(userCode: "ABCD-EFGH")
    XCTAssertTrue(state.status.isBusy)
    XCTAssertEqual(
      state.detailText,
      "Waiting for approval in your browser… If the page asks for a code, enter the one below.")

    state.status = .waitingForApproval(userCode: nil)
    XCTAssertEqual(state.detailText, "Waiting for approval in your browser…")

    state.status = .authFailed(message: "Timed out waiting for device authorization")
    XCTAssertFalse(state.status.isBusy)
    XCTAssertEqual(state.primaryActionTitle, "Retry sign-in")
    XCTAssertTrue(state.primaryActionEnabled)
    XCTAssertEqual(state.primaryAction, .beginConnection)

    state.status = .connected
    XCTAssertEqual(state.detailText, "Hermes is connected. Try your request again.")
  }

  func testFailureDetailTrimsTranscript() {
    let transcript = """
    Starting Hermes login via Nous Portal...
    Waiting for approval (polling every 5s)...
    expired_token: Device code has expired
    """
    XCTAssertEqual(
      HermesConnectService.failureDetail(fromTranscript: transcript),
      "Starting Hermes login via Nous Portal... expired_token: Device code has expired")
    XCTAssertEqual(HermesConnectService.failureDetail(fromTranscript: ""), "")
  }
}
