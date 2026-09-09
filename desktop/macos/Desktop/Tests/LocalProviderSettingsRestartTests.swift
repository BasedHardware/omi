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
  /// - Parameter localModelsFetcher: stands in for `AIProvider.fetchLocalModels` (the real
  ///   OpenAI-compatible `/models` request). Defaults to the real fetch so the two tests that
  ///   don't care about the fetch's outcome keep exercising it; the test that does care about
  ///   the auto-selected model list passes a deterministic stub instead.
  private func makeSettingsView(
    chatProvider: ChatProvider,
    localModelsFetcher: @escaping (String) async throws -> [String] = AIProvider.fetchLocalModels
  ) -> SettingsContentView {
    SettingsContentView(
      appState: AppState(),
      selectedSection: .constant(.aiChat),
      chatProvider: chatProvider,
      localModelsFetcher: localModelsFetcher,
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

  /// Regression test for the false "Could not apply local model change" error
  /// on first-time Local setup. Before the fix, `fetchLocalModelOptions`
  /// (SettingsContentView+FloatingBarAndChat.swift) auto-selected the first
  /// server-reported model when no model was configured yet *and* still
  /// called its own `onComplete`, so a Base URL commit with an empty model
  /// id fired two restart requests: one from the Model field's own
  /// `onChange(of: localLLMModelID)`, one from `onComplete`. The second was
  /// rejected by `AgentRuntimeProcess`'s single-flight guard
  /// (`BridgeError.restarting`), which `ChatProvider.restartLocalBridgeIfActive()`
  /// surfaced as a false error even though the first restart succeeded.
  ///
  /// SwiftUI's `.onChange(of: localLLMModelID)` only fires against a live
  /// view hierarchy this unit test never renders (same constraint the other
  /// tests in this file work around), so the auto-select's own restart is
  /// simulated the same direct way `testModelFieldChangeRequestsARestart`
  /// above does. The assertion that actually exercises the fix is
  /// `onCompleteCallCount`: it must be 0 once a model was auto-selected, or
  /// the Base URL commit is still firing two restarts for one commit.
  ///
  /// The completion signal below polls `localLLMModelID` (`@AppStorage`,
  /// backed by real `UserDefaults`), not `localModelOptions` (`@State`).
  /// `@State` has no persistent storage to write through until SwiftUI
  /// installs the view into a live hierarchy, which this unit test (like its
  /// siblings) never does; a write to it from here is silently dropped, so
  /// polling it can never observe the fetch settling. This is unrelated to
  /// the coalescing bug under test and unrelated to networking: it
  /// reproduces with a fully synchronous, non-async `@State` write read back
  /// on the same instance, with no `Task` or fetch involved at all.
  func testBaseURLCommitWithEmptyModelIdRestartsOnceAndShowsNoError() async {
    let defaults = UserDefaults.standard
    let previousModelId = defaults.string(forKey: AIProvider.localModelIDKey)
    defaults.removeObject(forKey: AIProvider.localModelIDKey)
    defer {
      if let previousModelId {
        defaults.set(previousModelId, forKey: AIProvider.localModelIDKey)
      } else {
        defaults.removeObject(forKey: AIProvider.localModelIDKey)
      }
    }

    let spy = RestartSpyChatProvider()
    // Stubs the model list directly instead of stubbing the OpenAI-compatible `/models`
    // endpoint over real networking: `AIProvider.fetchLocalModels` takes no session parameter
    // to inject a mock into, and a `URLProtocol` subclass registered against
    // `URLSession.shared` raced real loopback connection attempts inside the xctest process
    // (ECONNREFUSED arriving seconds later, well after the poll below had already given up).
    // The injected closure removes that race entirely.
    let view = makeSettingsView(
      chatProvider: spy,
      localModelsFetcher: { _ in ["stub-model-a", "stub-model-b"] }
    )
    XCTAssertEqual(view.localLLMModelID, "", "test setup: model id must start empty")

    var onCompleteCallCount = 0
    view.fetchLocalModelOptions(onComplete: {
      onCompleteCallCount += 1
      view.restartLocalBridgesIfActive()
    })

    // fetchLocalModelOptions has no completion signal besides onComplete, which the
    // coalescing fix may legitimately skip calling; poll localLLMModelID instead, since it is
    // set in the same MainActor.run block as onComplete's decision and (unlike
    // localModelOptions) is reliably observable from this unit test. The injected fetcher
    // above returns instantly (no real request), so this loop is bounded by Task-scheduling
    // latency, not a network timeout, and settles well inside the deadline.
    let deadline = Date().addingTimeInterval(6)
    while view.localLLMModelID.isEmpty && Date() < deadline {
      // omi-test-quality: wall-clock-wait -- fetchLocalModelOptions has no completion signal when the coalescing fix skips onComplete; polling is the only observable signal here
      try? await Task.sleep(nanoseconds: 50_000_000)
    }

    XCTAssertEqual(
      view.localLLMModelID, "stub-model-a",
      "empty model id must auto-select the first server-reported model")
    XCTAssertEqual(
      onCompleteCallCount, 0,
      "fetchLocalModelOptions must skip its own onComplete restart once it auto-selected a model, "
        + "or a Base URL commit with an empty model id fires two restarts")

    // The Model field's own onChange(of: localLLMModelID) ->
    // restartLocalBridgesIfActive() is what actually requests the one
    // restart this auto-select is supposed to cause; simulate it directly
    // (see the doc comment above) and confirm it is the only restart.
    let restarted = expectation(description: "restart requested")
    spy.onRestart = { restarted.fulfill() }
    view.restartLocalBridgesIfActive()
    await fulfillment(of: [restarted], timeout: 2)

    XCTAssertEqual(
      spy.restartCallCount, 1,
      "exactly one restart total for a Base URL commit that also auto-selects a first model")
    XCTAssertNil(
      spy.errorMessage,
      "a coalesced restart must not surface the false 'Could not apply local model change' error")
  }
}
