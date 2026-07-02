import XCTest

@testable import Omi_Computer

final class LocalAgentProviderRoutingTests: XCTestCase {
    func testClassifyTaskDetectsCoding() {
        XCTAssertEqual(
            LocalAgentProviderRouting.classifyTask("debug this python script"),
            .coding
        )
    }

    func testClassifyTaskDetectsAutomation() {
        XCTAssertEqual(
            LocalAgentProviderRouting.classifyTask("automate sending this email"),
            .automation
        )
    }

    func testModelBriefMentioningHermesDoesNotCountAsExplicitUserRequest() {
        let env = ["OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex"]
        let resolution = LocalAgentProviderRouting.resolveSpawn(
            brief: "Use Hermes to refactor the auth module",
            requestedProvider: .hermes,
            userRequestText: nil,
            title: nil,
            environment: env,
            fileManager: FileManager(),
            homeDirectory: "/tmp/omi-routing-test"
        )

        guard case .spawn(let plan) = resolution else {
            return XCTFail("Expected spawn fallback to Codex, got \(resolution)")
        }
        XCTAssertEqual(plan.selectedProvider, .codex)
        XCTAssertTrue(plan.usedFallback)
    }

    func testExplicitHermesInUserTextStillRequiresSetupWhenMissing() {
        let resolution = LocalAgentProviderRouting.resolveSpawn(
            brief: "fix the bug",
            requestedProvider: .hermes,
            userRequestText: "use hermes to fix the bug",
            title: nil,
            environment: [:],
            fileManager: FileManager(),
            homeDirectory: "/tmp/omi-routing-test"
        )

        guard case .setupRequired(let provider, let prompt, _) = resolution else {
            return XCTFail("Expected setupRequired, got \(resolution)")
        }
        XCTAssertEqual(provider, .hermes)
        XCTAssertTrue(prompt.contains("Hermes"))
    }

    func testSmartRoutingFallsBackWhenRequestedProviderMissing() {
        let env = ["OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex"]
        let resolution = LocalAgentProviderRouting.resolveSpawn(
            brief: "write a script to parse logs",
            requestedProvider: .hermes,
            userRequestText: "write a script to parse logs",
            title: "Log parser",
            environment: env,
            fileManager: FileManager(),
            homeDirectory: "/tmp/omi-routing-test"
        )

        guard case .spawn(let plan) = resolution else {
            return XCTFail("Expected spawn, got \(resolution)")
        }
        XCTAssertEqual(plan.selectedProvider, .codex)
        XCTAssertTrue(plan.usedFallback)
        XCTAssertNotNil(plan.fallbackNote)
        XCTAssertEqual(plan.harnessOverride, .codex)
    }

    func testSmartRoutingPicksCodexForCodingWhenAvailable() {
        let env = [
            "OMI_CODEX_ADAPTER_COMMAND": "/tmp/codex",
            "OMI_OPENCLAW_ADAPTER_COMMAND": "/tmp/openclaw",
        ]
        let resolution = LocalAgentProviderRouting.resolveSpawn(
            brief: "review this swift api change",
            requestedProvider: nil,
            userRequestText: "review this swift api change",
            title: nil,
            environment: env,
            fileManager: FileManager(),
            homeDirectory: "/tmp/omi-routing-test"
        )

        guard case .spawn(let plan) = resolution else {
            return XCTFail("Expected spawn, got \(resolution)")
        }
        XCTAssertEqual(plan.selectedProvider, .codex)
        XCTAssertFalse(plan.usedFallback)
    }

    func testSpawnContextAdvancesFallbackChain() {
        var context = AgentSpawnContext(
            taskKind: .coding,
            explicitProvider: nil,
            fallbackChain: [.codex, .openclaw, nil],
            attemptedHarnesses: [.codex]
        )
        XCTAssertEqual(context.nextFallback(after: .codex), .some(.openclaw))
        context.recordAttempt(.openclaw)
        XCTAssertEqual(context.nextFallback(after: .openclaw), .some(nil))
    }

    func testIsRetriableSpawnFailureMatchesInfrastructureErrors() {
        XCTAssertTrue(LocalAgentProviderRouting.isRetriableSpawnFailure("AI not available: adapter failed"))
        XCTAssertTrue(LocalAgentProviderRouting.isRetriableSpawnFailure("ENOENT: no such file or directory"))
        XCTAssertTrue(LocalAgentProviderRouting.isRetriableSpawnFailure("Failed to start child process"))
        XCTAssertFalse(LocalAgentProviderRouting.isRetriableSpawnFailure("Could not find the email thread"))
        XCTAssertFalse(LocalAgentProviderRouting.isRetriableSpawnFailure("Could not parse adapter response: invalid JSON"))
    }
}
