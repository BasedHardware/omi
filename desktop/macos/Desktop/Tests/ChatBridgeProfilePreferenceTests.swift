import XCTest

@testable import Omi_Computer

/// Regression coverage for immutable-session provider preferences.
final class ChatBridgeProfilePreferenceTests: XCTestCase {
  func testProviderPreferenceAppliesToNewSessionsWithoutDaemonRestart() {
    XCTAssertEqual(AgentExecutionProfileLifecycle.defaultPreferenceAppliesTo, "new_sessions")
    XCTAssertFalse(AgentExecutionProfileLifecycle.defaultPreferenceChangeRequiresDaemonRestart)
  }

  func testPinnedSessionOwnsQuotaAndTelemetryAcrossPreferenceFlips() {
    // `providerMode` is passed explicitly (the actual running provider at
    // construction time), not re-derived from UserDefaults, so a run's
    // accounting stays pinned to what was actually running even if the
    // Settings preference (and later, the actually-running provider) moves
    // on to something else before this policy is read again.
    let existingHermesRun = ChatRunAccountingPolicy(
      pinnedAdapterID: AgentAdapterId.hermes.rawValue,
      providerMode: "omi"
    )
    XCTAssertFalse(existingHermesRun.usesOmiAccountQuota)
    XCTAssertFalse(existingHermesRun.recordsPersonalProviderUsage)

    let inFlightOmiRun = ChatRunAccountingPolicy(
      pinnedAdapterID: AgentAdapterId.piMono.rawValue,
      providerMode: "omi"
    )
    XCTAssertTrue(inFlightOmiRun.usesOmiAccountQuota)
    XCTAssertFalse(inFlightOmiRun.recordsPersonalProviderUsage)

    // Constructed as though the actual running provider were already
    // "omi-local": even a piMono-pinned run must not bill Omi's quota once
    // the running process has actually switched to Local.
    let localRun = ChatRunAccountingPolicy(
      pinnedAdapterID: AgentAdapterId.piMono.rawValue,
      providerMode: "omi-local"
    )
    XCTAssertFalse(localRun.usesOmiAccountQuota)
    XCTAssertFalse(localRun.recordsPersonalProviderUsage)

    let existingPersonalClaudeRun = ChatRunAccountingPolicy(
      pinnedAdapterID: AgentAdapterId.acp.rawValue,
      providerMode: "omi"
    )
    XCTAssertFalse(existingPersonalClaudeRun.usesOmiAccountQuota)
    XCTAssertTrue(existingPersonalClaudeRun.recordsPersonalProviderUsage)
  }
}
