import Foundation
import XCTest

@testable import Omi_Computer

/// Spies on the shared-runtime restart request without touching AgentBridge or
/// AgentRuntimeProcess: `ChatProvider` is not `final`, and
/// `restartLocalBridgeIfActive()` is the exact seam
/// `SettingsContentView.restartLocalBridgesIfActive()` (see
/// SettingsContentView+FloatingBarAndChat.swift) calls through. Overriding it
/// here exercises the real production wiring above this point (the Settings
/// field's onSubmit/onChange handler and, for Base URL, the model-list
/// refetch that must complete first) without spawning a real agent
/// subprocess.
@MainActor
private final class RestartSpyChatProvider: ChatProvider {
  private(set) var restartCallCount = 0
  var onRestart: (() -> Void)?

  override func restartLocalBridgeIfActive() async {
    restartCallCount += 1
    onRestart?()
  }
}

@MainActor
final class LocalProviderSettingsRestartTests: XCTestCase {
  private func makeSettingsView(chatProvider: ChatProvider) -> SettingsContentView {
    SettingsContentView(
      appState: AppState(),
      selectedSection: .constant(.aiChat),
      chatProvider: chatProvider,
      showResetOnboardingConfirm: .constant(false)
    )
  }

  /// Baseline: the Model field's `.onChange(of: localLLMModelID) { restartLocalBridgesIfActive() }`
  /// (SettingsContentView+FloatingBarAndChat.swift) calls this directly, no
  /// refetch involved. The Base URL test below mirrors this expectation.
  func testModelFieldChangeRequestsARestart() async {
    let spy = RestartSpyChatProvider()
    let restarted = expectation(description: "restart requested")
    spy.onRestart = { restarted.fulfill() }
    let view = makeSettingsView(chatProvider: spy)

    view.restartLocalBridgesIfActive()

    await fulfillment(of: [restarted], timeout: 2)
    XCTAssertEqual(spy.restartCallCount, 1)
  }

  /// Regression test for the bug class `5f3abca24a` fixed for the model
  /// fields but missed for Base URL: committing the field (onSubmit, or
  /// losing focus without pressing Enter) must still request a restart, so a
  /// user who repoints Base URL doesn't keep talking to the old server. The
  /// restart must fire only after the model-list refetch settles (success or
  /// failure), which `fetchLocalModelOptions(onComplete:)` guarantees by
  /// running the callback in both its success and catch branches.
  func testBaseURLFieldCommitRequestsARestartAfterTheModelListRefetch() async {
    let spy = RestartSpyChatProvider()
    let restarted = expectation(description: "restart requested")
    spy.onRestart = { restarted.fulfill() }
    let view = makeSettingsView(chatProvider: spy)

    // Mirrors the Base URL TextField's onSubmit/focus-loss handler
    // (SettingsContentView+FloatingBarAndChat.swift). Uses the default local
    // base URL; regardless of whether anything answers on localhost:1234 in
    // this environment, fetchLocalModelOptions calls onComplete on both its
    // success and failure paths, so the restart assertion holds either way.
    view.fetchLocalModelOptions(onComplete: view.restartLocalBridgesIfActive)

    // Bounded above the fetch's own 5s request timeout.
    await fulfillment(of: [restarted], timeout: 6)
    XCTAssertEqual(spy.restartCallCount, 1)
  }
}
