import Foundation
import XCTest

@testable import Omi_Computer

/// Stubs the OpenAI-compatible `/models` endpoint `AIProvider.fetchLocalModels`
/// hits via `URLSession.shared` (it takes no session parameter to inject a
/// mock into). Registering a `URLProtocol` subclass intercepts requests for
/// `URLSession.shared`'s default configuration for the lifetime of the
/// registration.
private final class LocalModelsStubProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool {
    request.url?.path.hasSuffix("/models") == true
  }

  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let body = Data(#"{"data":[{"id":"stub-model-a"},{"id":"stub-model-b"}]}"#.utf8)
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil,
      headerFields: ["Content-Type": "application/json"])!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

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
  func testBaseURLCommitWithEmptyModelIdRestartsOnceAndShowsNoError() async {
    URLProtocol.registerClass(LocalModelsStubProtocol.self)
    defer { URLProtocol.unregisterClass(LocalModelsStubProtocol.self) }

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
    let view = makeSettingsView(chatProvider: spy)
    XCTAssertEqual(view.localLLMModelID, "", "test setup: model id must start empty")

    var onCompleteCallCount = 0
    view.fetchLocalModelOptions(onComplete: {
      onCompleteCallCount += 1
      view.restartLocalBridgesIfActive()
    })

    // fetchLocalModelOptions has no completion signal besides onComplete,
    // which the coalescing fix may legitimately skip calling; poll the
    // populated model list instead (set in the same MainActor.run block as
    // the auto-select and the onComplete decision), bounded well above the
    // fetch's own 5s request timeout.
    let deadline = Date().addingTimeInterval(6)
    while view.localModelOptions.isEmpty && Date() < deadline {
      try? await Task.sleep(nanoseconds: 50_000_000)
    }

    XCTAssertEqual(view.localModelOptions, ["stub-model-a", "stub-model-b"])
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
