import XCTest

@testable import Omi_Computer

final class LocalAgentProviderInstallerTests: XCTestCase {
  // MARK: - Confirmation dialog content (the code-level consent gate)

  func testConfirmationTextShowsExactCommandAndSourceDomain() {
    for provider in AgentPillsManager.orderedDirectedProviders {
      let text = LocalAgentProviderInstaller.confirmationText(for: provider)
      // The dialog must show the LITERAL command that will run — no summary.
      XCTAssertTrue(text.contains(provider.unattendedInstallCommand))
      XCTAssertTrue(text.contains("Downloads and runs software from \(provider.installSourceDomain)."))
    }
    XCTAssertEqual(AgentPillsManager.DirectedProvider.hermes.installSourceDomain, "hermes-agent.nousresearch.com")
    XCTAssertEqual(AgentPillsManager.DirectedProvider.openclaw.installSourceDomain, "openclaw.ai")
    XCTAssertEqual(AgentPillsManager.DirectedProvider.codex.installSourceDomain, "registry.npmjs.org")
  }

  func testConsentRuleMatchesTheTSManifestGuideline() throws {
    // ONE consent sentence everywhere. The TS manifest keeps its own copy —
    // keep them literally identical so neither side drifts.
    let manifestURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("agent/src/runtime/omi-tool-manifest.ts")
    let manifest = try String(contentsOf: manifestURL, encoding: .utf8)
    XCTAssertTrue(manifest.contains("\"\(LocalAgentProviderInstaller.consentRule)\""))
  }

  // MARK: - Install subprocess environment

  func testInstallPATHCoversDetectorDirectoriesAndDedupes() {
    let home = "/Users/test"
    let path = LocalAgentProviderInstaller.installPATH(
      existingPath: "/usr/bin:/opt/homebrew/bin",
      homeDirectory: home)
    let elements = path.split(separator: ":").map(String.init)

    // Every authoritative detection directory is on the install PATH, so a
    // fresh install lands somewhere the detector can already see.
    for dir in LocalAgentProviderDetector.adapterActivationSearchDirectories(homeDirectory: home) {
      XCTAssertTrue(elements.contains(dir), "missing detector dir \(dir)")
    }
    // Standard system dirs are appended; inherited entries are deduplicated.
    XCTAssertTrue(elements.contains("/bin"))
    XCTAssertTrue(elements.contains("/usr/sbin"))
    XCTAssertEqual(elements.filter { $0 == "/usr/bin" }.count, 1)
    XCTAssertEqual(elements.filter { $0 == "/opt/homebrew/bin" }.count, 1)
  }

  func testInstallPATHWorksWithoutInheritedPath() {
    let path = LocalAgentProviderInstaller.installPATH(existingPath: nil, homeDirectory: "/Users/test")
    let elements = path.split(separator: ":").map(String.init)
    XCTAssertTrue(elements.contains("/usr/bin"))
    XCTAssertTrue(elements.contains("/Users/test/.local/bin"))
    XCTAssertFalse(elements.contains(""))
  }

  func testInstallEnvironmentIsAnAllowlistNeverWholesaleInheritance() {
    let base = [
      // One entry per allowlisted key, so every key's pass-through is pinned.
      "PATH": "/usr/bin:/opt/homebrew/bin",
      "HOME": "/Users/other",
      "TMPDIR": "/var/folders/xx/T/",
      "USER": "test",
      "LOGNAME": "test",
      "SHELL": "/bin/zsh",
      "LANG": "en_US.UTF-8",
      "LC_ALL": "en_US.UTF-8",
      "LC_CTYPE": "UTF-8",
      // Credentials/tokens that must NOT cross the install boundary — the
      // install command runs third-party downloaded code.
      "OMI_API_KEY": "secret",
      "OMI_DESKTOP_API_URL": "https://example.com",
      "ANTHROPIC_API_KEY": "secret",
      "OPENAI_API_KEY": "secret",
      "AWS_SECRET_ACCESS_KEY": "secret",
      "GITHUB_TOKEN": "secret",
      // Tempting-but-dangerous vars a future dev might reach for:
      // NODE_OPTIONS/npm_config_* inject code into npm runs, SSH_AUTH_SOCK
      // exposes the user's agent, proxy URLs embed credentials.
      "NODE_OPTIONS": "--require /tmp/evil.js",
      "npm_config_registry": "https://registry.evil.example",
      "SSH_AUTH_SOCK": "/tmp/ssh-agent.sock",
      "HTTPS_PROXY": "http://user:secret@proxy.example:8080",
    ]
    let environment = LocalAgentProviderInstaller.installEnvironment(
      base: base, homeDirectory: "/Users/test")

    // Exactly the allowlist survives — nothing else leaks through.
    XCTAssertEqual(
      Set(environment.keys),
      ["PATH", "HOME", "TMPDIR", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE"])
    // HOME is the app's real home dir, PATH is the rebuilt install PATH.
    XCTAssertEqual(environment["HOME"], "/Users/test")
    XCTAssertEqual(
      environment["PATH"],
      LocalAgentProviderInstaller.installPATH(
        existingPath: "/usr/bin:/opt/homebrew/bin", homeDirectory: "/Users/test"))
  }

  func testInstallEnvironmentWorksFromAnEmptyBase() {
    let environment = LocalAgentProviderInstaller.installEnvironment(
      base: [:], homeDirectory: "/Users/test")
    XCTAssertEqual(environment["HOME"], "/Users/test")
    XCTAssertNotNil(environment["PATH"])
    XCTAssertNil(environment["TMPDIR"])
  }

  func testInstallEnvironmentAllowlistGrowthRequiresAConsciousTestEdit() {
    // The allowlist IS the security boundary: every addition crosses into
    // third-party installer code, so growing it must fail a test.
    XCTAssertEqual(
      LocalAgentProviderInstaller.installEnvironmentAllowlistKeys,
      ["TMPDIR", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE"])
  }

  // MARK: - Source contract: NSAlert gate + Process, never an agent

  func testInstallerGatesOnNativeDialogAndRunsProcessDirectly() throws {
    let source = try installerSource()

    // NSAlert consent gate on the main actor with explicit Install/Cancel;
    // only an explicit click proceeds.
    XCTAssertTrue(source.contains("let alert = NSAlert()"))
    XCTAssertTrue(source.contains(#"alert.messageText = "Install \(provider.displayName)?""#))
    XCTAssertTrue(source.contains(#"alert.addButton(withTitle: "Install")"#))
    XCTAssertTrue(source.contains(#"alert.addButton(withTitle: "Cancel")"#))
    XCTAssertTrue(source.contains("guard response == .alertFirstButtonReturn else"))

    // Deterministic Process install: /bin/bash -c with the code-owned
    // command — never a login shell, never an agent pill.
    XCTAssertTrue(source.contains(#"URL(fileURLWithPath: "/bin/bash")"#))
    XCTAssertTrue(source.contains(#"["-c", provider.unattendedInstallCommand]"#))
    XCTAssertFalse(source.contains("AgentPillsManager.shared.spawn"))
    XCTAssertFalse(source.contains("ChatProvider"))

    // The subprocess environment is built through the allowlist — the app
    // environment appears exactly once, as the filter input, and is never
    // assigned wholesale.
    XCTAssertTrue(source.contains("process.environment = installEnvironment("))
    XCTAssertEqual(
      source.components(separatedBy: "ProcessInfo.processInfo.environment").count - 1, 1,
      "the app environment must appear once, as installEnvironment's base argument")

    // Timeout tears the whole process tree down.
    XCTAssertTrue(source.contains("installTimeoutSeconds: TimeInterval = 600"))
    XCTAssertTrue(source.contains("terminateProcessTree(process)"))
    XCTAssertTrue(source.contains("kill(-pid, SIGTERM)"))

    // Verification is the shared detector — no agent-side probing — and a
    // successful install re-warms the hub session directly.
    XCTAssertTrue(source.contains("LocalAgentProviderDetector.availability(for: provider)"))
    XCTAssertTrue(source.contains("RealtimeHubController.shared.refreshForLocalAgentProviderChange()"))

    // Outcomes reach the user through the existing notification surface.
    XCTAssertTrue(source.contains("NotificationService.shared.sendNotification("))
    XCTAssertTrue(source.contains(#"title: "\(provider.displayName) installed""#))
    XCTAssertTrue(source.contains(#"title: "\(provider.displayName) install failed""#))
    XCTAssertTrue(source.contains("Install guide: \\(provider.installDocsURL)"))
  }

  private func installerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/LocalAgentProviderInstaller.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
