import XCTest

@testable import Omi_Computer

/// Regression coverage for immutable-session provider preferences.
final class ChatBridgeProfilePreferenceTests: XCTestCase {
  func testProviderPreferenceAppliesToNewSessionsWithoutDaemonRestart() {
    XCTAssertEqual(AgentExecutionProfileLifecycle.defaultPreferenceAppliesTo, "new_sessions")
    XCTAssertFalse(AgentExecutionProfileLifecycle.defaultPreferenceChangeRequiresDaemonRestart)
  }

  func testPinnedSessionOwnsQuotaAndTelemetryAcrossPreferenceFlips() {
    let suite = "ChatBridgeProfilePreferenceTests.\(UUID().uuidString)"
    let defaults = try! XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }

    let existingHermesRun = ChatRunAccountingPolicy(
      pinnedAdapterID: AgentAdapterId.hermes.rawValue
    )
    defaults.set(ChatProvider.BridgeMode.piMono.rawValue, forKey: "chatBridgeMode")
    XCTAssertFalse(existingHermesRun.usesOmiAccountQuota)
    XCTAssertFalse(existingHermesRun.recordsPersonalProviderUsage)

    let inFlightOmiRun = ChatRunAccountingPolicy(
      pinnedAdapterID: AgentAdapterId.piMono.rawValue
    )
    defaults.set(ChatProvider.BridgeMode.openClaw.rawValue, forKey: "chatBridgeMode")
    XCTAssertTrue(inFlightOmiRun.usesOmiAccountQuota)
    XCTAssertFalse(inFlightOmiRun.recordsPersonalProviderUsage)

    let existingPersonalClaudeRun = ChatRunAccountingPolicy(
      pinnedAdapterID: AgentAdapterId.acp.rawValue
    )
    defaults.set(ChatProvider.BridgeMode.piMono.rawValue, forKey: "chatBridgeMode")
    XCTAssertFalse(existingPersonalClaudeRun.usesOmiAccountQuota)
    XCTAssertTrue(existingPersonalClaudeRun.recordsPersonalProviderUsage)
  }
}
