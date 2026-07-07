import XCTest

@testable import Omi_Computer

/// Covers detection of OpenClaw's onboarded state (installed-but-not-onboarded
/// vs. genuinely set up) and the non-interactive onboard command.
final class OpenClawOnboardProbeTests: XCTestCase {

    private func makeHome() throws -> String {
        let home = NSTemporaryDirectory() + "omi-openclaw-\(UUID().uuidString)"
        try FileManager.default.createDirectory(atPath: home + "/.openclaw", withIntermediateDirectories: true)
        return home
    }

    private func writeConfig(_ home: String, _ json: String) throws {
        try json.write(toFile: home + "/.openclaw/openclaw.json", atomically: true, encoding: .utf8)
    }

    func testOnboardedWhenGatewayAndModelPresent() throws {
        let home = try makeHome()
        defer { try? FileManager.default.removeItem(atPath: home) }
        try writeConfig(home, """
        {"gateway":{"port":18789,"auth":{"mode":"token"}},
         "agents":{"defaults":{"model":{"primary":"anthropic/claude-opus-4-8"}}}}
        """)
        XCTAssertTrue(OpenClawOnboardProbe.isOnboarded(environment: [:], homeDirectory: home))
    }

    func testNotOnboardedWhenConfigMissing() throws {
        let home = try makeHome()
        defer { try? FileManager.default.removeItem(atPath: home) }
        // Bare binary install (`--no-onboard`) writes no config.
        XCTAssertFalse(OpenClawOnboardProbe.isOnboarded(environment: [:], homeDirectory: home))
    }

    func testNotOnboardedWhenGatewayMissing() throws {
        let home = try makeHome()
        defer { try? FileManager.default.removeItem(atPath: home) }
        try writeConfig(home, """
        {"agents":{"defaults":{"model":{"primary":"anthropic/claude-opus-4-8"}}}}
        """)
        XCTAssertFalse(OpenClawOnboardProbe.isOnboarded(environment: [:], homeDirectory: home))
    }

    func testNotOnboardedWhenModelMissing() throws {
        let home = try makeHome()
        defer { try? FileManager.default.removeItem(atPath: home) }
        try writeConfig(home, """
        {"gateway":{"port":18789}}
        """)
        XCTAssertFalse(OpenClawOnboardProbe.isOnboarded(environment: [:], homeDirectory: home))
    }

    func testRespectsConfigPathOverride() throws {
        let dir = NSTemporaryDirectory() + "omi-openclaw-ovr-\(UUID().uuidString)"
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(atPath: dir) }
        let cfg = dir + "/custom.json"
        try """
        {"gateway":{"port":19001},"agents":{"defaults":{"model":{"primary":"x/y"}}}}
        """.write(toFile: cfg, atomically: true, encoding: .utf8)
        XCTAssertTrue(OpenClawOnboardProbe.isOnboarded(
            environment: ["OPENCLAW_CONFIG_PATH": cfg], homeDirectory: "/nonexistent"))
    }

    func testOnboardArgumentsAreNonInteractiveAndScriptable() {
        let args = OpenClawConnectService.onboardArguments
        XCTAssertEqual(args.first, "onboard")
        XCTAssertTrue(args.contains("--non-interactive"))
        XCTAssertTrue(args.contains("--accept-risk"))
        XCTAssertTrue(args.contains("--install-daemon"))
        // Auth reuses the local Claude sign-in (the app's native default agent).
        let idx = args.firstIndex(of: "--auth-choice")
        XCTAssertNotNil(idx)
        if let idx { XCTAssertEqual(args[idx + 1], "anthropic-cli") }
    }

    /// The no-Claude-Code fallback: a user-runnable Terminal command using an
    /// OpenRouter API key (real `openclaw onboard` flags), with a placeholder
    /// the user replaces — the app never handles the key.
    func testManualModelSetupCommandUsesOpenRouterKeyChoice() {
        let command = OpenClawConnectService.manualModelSetupCommand
        XCTAssertTrue(command.hasPrefix("openclaw onboard "))
        XCTAssertTrue(command.contains("--non-interactive"))
        XCTAssertTrue(command.contains("--accept-risk"))
        XCTAssertTrue(command.contains("--auth-choice openrouter-api-key"))
        XCTAssertTrue(command.contains(
            "--openrouter-api-key \(OpenClawConnectService.manualSetupKeyPlaceholder)"))
        XCTAssertTrue(command.contains("--install-daemon"))
        // Pre-typed via zsh `print -z` inside single quotes and an AppleScript
        // double-quoted string — the command must not need escaping in either.
        XCTAssertFalse(command.contains("'"))
        XCTAssertFalse(command.contains("\""))
        XCTAssertFalse(command.contains("\\"))
    }

    func testManualModelSetupPromptStatusDrivesTerminalAction() {
        let plan = AgentPillsManager.DirectedProvider.openclaw.authenticationPlan
        var state = AgentInstallPromptState(plan: plan)
        state.status = .needsManualModelSetup(
            command: OpenClawConnectService.manualModelSetupCommand)
        XCTAssertEqual(state.primaryActionTitle, "Open Terminal")
        XCTAssertEqual(state.primaryAction, .openTerminalSetup)
        XCTAssertTrue(state.primaryActionEnabled)
        XCTAssertFalse(state.status.isBusy)
        XCTAssertEqual(state.status.automationValue, "needsManualModelSetup")
    }
}
