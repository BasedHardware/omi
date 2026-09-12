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
  ///   OpenAI-compatible `/models` request). Defaults to the real fetch; every test below that
  ///   actually calls `fetchLocalModelOptions` passes a deterministic stub instead, since a live
  ///   network call would make the test depend on whether anything answers on localhost:1234.
  ///   `testModelFieldChangeRequestsARestart` never calls the fetch at all, so the default is
  ///   unused there.
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
  ///
  /// Uses the same injected `localModelsFetcher` stub as
  /// `testBaseURLCommitWithEmptyModelIdRestartsOnce` below
  /// instead of the real `/models` HTTP request: a live network call made
  /// this test hermetic-unsafe (it depended on whether anything happened to
  /// answer on localhost:1234) and slower than it needed to be.
  ///
  /// A configured model id is required going in: `fetchLocalModelOptions`
  /// only calls `onComplete` when a model was already configured (see its
  /// doc comment), auto-selecting instead when it was empty, which needs a
  /// live view hierarchy to observe (that path is
  /// `testBaseURLCommitWithEmptyModelIdRestartsOnce`'s job).
  func testBaseURLFieldCommitRequestsARestartAfterTheModelListRefetch() async {
    let defaults = UserDefaults.standard
    let previousModelId = defaults.string(forKey: AIProvider.localModelIDKey)
    defaults.set("existing-model", forKey: AIProvider.localModelIDKey)
    defer {
      if let previousModelId {
        defaults.set(previousModelId, forKey: AIProvider.localModelIDKey)
      } else {
        defaults.removeObject(forKey: AIProvider.localModelIDKey)
      }
    }

    let spy = RestartSpyChatProvider()
    let restarted = expectation(description: "restart requested")
    spy.onRestart = { restarted.fulfill() }
    let view = makeSettingsView(
      chatProvider: spy,
      localModelsFetcher: { _ in ["existing-model", "stub-model-b"] }
    )

    // Mirrors the Base URL TextField's onSubmit/focus-loss handler
    // (SettingsContentView+FloatingBarAndChat.swift). The stub fetcher above
    // resolves instantly, so fetchLocalModelOptions calls onComplete without
    // any real request or wait.
    view.fetchLocalModelOptions(onComplete: view.restartLocalBridgesIfActive)

    await fulfillment(of: [restarted], timeout: 2)
    XCTAssertEqual(spy.restartCallCount, 1)
  }

  /// `commitLocalBaseURL()` (what the TextField's onSubmit/focus-loss
  /// handler actually calls, see SettingsContentView+FloatingBarAndChat.swift)
  /// must itself drive a fetch-then-restart, exactly like calling
  /// `fetchLocalModelOptions(onComplete: restartLocalBridgesIfActive)`
  /// directly does in the test above.
  func testCommitLocalBaseURLRequestsARestart() async {
    let defaults = UserDefaults.standard
    let previousModelId = defaults.string(forKey: AIProvider.localModelIDKey)
    defaults.set("existing-model", forKey: AIProvider.localModelIDKey)
    defer {
      if let previousModelId {
        defaults.set(previousModelId, forKey: AIProvider.localModelIDKey)
      } else {
        defaults.removeObject(forKey: AIProvider.localModelIDKey)
      }
    }

    let spy = RestartSpyChatProvider()
    let restarted = expectation(description: "restart requested")
    spy.onRestart = { restarted.fulfill() }
    let view = makeSettingsView(
      chatProvider: spy,
      localModelsFetcher: { _ in ["existing-model", "stub-model-b"] }
    )

    view.commitLocalBaseURL()

    await fulfillment(of: [restarted], timeout: 2)
    XCTAssertEqual(spy.restartCallCount, 1)
  }

  /// Companion to the test above: `fetchLocalModelOptions`'s catch branch
  /// (the server is unreachable or the base URL is wrong) must still call
  /// `onComplete` and request a restart, exactly like its success branch
  /// does. A stub that always resolves cannot exercise this path; this one
  /// always throws.
  ///
  /// Only the restart is asserted, not `localModelsFetchFailed`: that is
  /// `@State`, which (like `localModelOptions` elsewhere in this file) is
  /// silently dropped when written from a test that never installs the view
  /// into a live SwiftUI hierarchy, so it cannot be observed here.
  func testBaseURLFieldCommitRequestsARestartWhenTheModelListRefetchFails() async {
    let spy = RestartSpyChatProvider()
    let restarted = expectation(description: "restart requested")
    spy.onRestart = { restarted.fulfill() }
    let view = makeSettingsView(
      chatProvider: spy,
      localModelsFetcher: { _ in throw URLError(.cannotConnectToHost) }
    )

    view.fetchLocalModelOptions(onComplete: view.restartLocalBridgesIfActive)

    await fulfillment(of: [restarted], timeout: 2)
    XCTAssertEqual(spy.restartCallCount, 1)
  }

  /// Regression test for a Base URL commit with an empty model id firing two
  /// restart requests instead of one. Before the fix, `fetchLocalModelOptions`
  /// (SettingsContentView+FloatingBarAndChat.swift) auto-selected the first
  /// server-reported model when no model was configured yet *and* still
  /// called its own `onComplete`, so the commit fired one restart from the
  /// Model field's own `onChange(of: localLLMModelID)` and a second,
  /// redundant one from `onComplete`. (That second restart used to be
  /// rejected by `AgentRuntimeProcess`'s single-flight guard as
  /// `BridgeError.restarting`, which `ChatProvider.restartLocalBridgeIfActive()`
  /// surfaced as a false "Could not apply local model change" error — this
  /// test only asserts the restart count now; see git history if you need the
  /// error-surfacing behavior covered separately.)
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
  func testBaseURLCommitWithEmptyModelIdRestartsOnce() async {
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
  }
}
