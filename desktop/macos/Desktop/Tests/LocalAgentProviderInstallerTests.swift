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
