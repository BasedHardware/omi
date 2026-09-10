import XCTest

@testable import Omi_Computer

/// Returns a fixed HTTP status for every request, so a test can pin how the
/// desktop app's tool-call error handling behaves on a specific server
/// response (here, 402 Payment Required) without a real backend.
private final class FixedStatusURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _statusCode = 402
  private nonisolated(unsafe) static var _requestCount = 0

  static func reset(statusCode: Int = 402) {
    lock.withLock {
      _statusCode = statusCode
      _requestCount = 0
    }
  }

  static var requestCount: Int {
    lock.withLock { _requestCount }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let statusCode = Self.lock.withLock {
      Self._requestCount += 1
      return Self._statusCode
    }
    guard
      let response = HTTPURLResponse(
        url: request.url!, statusCode: statusCode, httpVersion: nil,
        headerFields: ["Content-Type": "application/json"])
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data(#"{"detail":"payment required"}"#.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

/// Free-tier quota exists to meter Omi's cloud model usage. When the Local
/// provider is active and a feature runs entirely against the user's own
/// server, it must not be blocked or counted against that quota. These pin
/// the predicates that decide that for each gated feature, and the
/// regressions that keep every other provider (and connector synthesis
/// opted into the cloud) on the gates they already had.
@MainActor final class LocalProviderPaywallTests: XCTestCase {
  private let paywallKey = "desktop_isPaywalled"
  private let bridgeModeKey = "chatBridgeMode"

  override func tearDown() async throws {
    UserDefaults.standard.removeObject(forKey: paywallKey)
    UserDefaults.standard.removeObject(forKey: bridgeModeKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.localBackendURLKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.connectorSynthesisModeKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.cloudAssistModeKey)
    for p in BYOKProvider.allCases {
      UserDefaults.standard.removeObject(forKey: p.storageKey)
    }
    UserDefaults.standard.removeObject(forKey: .byokLLMProvider)
    APIKeyService.persistEnrolledFingerprints([:])
    FloatingBarUsageLimiter.shared.reset()
    ManagedProactivityDecisionSource.setOverride(nil)
    NegativeFeedbackRemediationFeature.testOverride = nil
  }

  private func exhaustedFreeQuota() throws -> APIClient.ChatUsageQuota {
    let json: [String: Any] = [
      "plan": "Free",
      "plan_type": "basic",
      "unit": "questions",
      "used": 30.0,
      "limit": 30.0,
      "percent": 100.0,
      "allowed": false,
    ]
    let data = try JSONSerialization.data(withJSONObject: json)
    return try JSONDecoder().decode(APIClient.ChatUsageQuota.self, from: data)
  }

  // MARK: - AIProvider.isLocalProviderActive

  func testIsLocalProviderActiveReflectsBridgeMode() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    XCTAssertTrue(AIProvider.isLocalProviderActive)

    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    XCTAssertFalse(AIProvider.isLocalProviderActive)
  }

  // MARK: - Screen capture / screenshot interpretation

  func testScreenCaptureExemptWhenLocalProviderActiveEvenIfPaywalled() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    XCTAssertTrue(
      AppState.isScreenCaptureExemptFromPaywall,
      "screenshot interpretation now runs against the user's own server under Local "
        + "(vision-subagent delegation), so it must not be paywalled")
  }

  /// Regression: every other provider stays on the general paywall check —
  /// this branch never claimed to serve screenshots locally.
  func testScreenCaptureStaysGatedForOmiProviderWhenPaywalled() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    XCTAssertFalse(AppState.isScreenCaptureExemptFromPaywall)
  }

  func testScreenCaptureExemptWhenNotPaywalledRegardlessOfProvider() {
    UserDefaults.standard.set(false, forKey: paywallKey)
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    XCTAssertTrue(AppState.isScreenCaptureExemptFromPaywall)
  }

  /// Once the user opts cloud-assisted features on, screen-capture-driven
  /// proactive features (task/memory/insight/suggestion extraction) go back
  /// to Omi's Gemini proxy, so screen capture is metered again exactly like
  /// a cloud user — the exemption is `isLocalProviderActive` alone no longer.
  func testScreenCaptureNotExemptWhenLocalProviderActiveButCloudAssistOn() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.cloud.rawValue, forKey: AIProvider.cloudAssistModeKey)
    XCTAssertFalse(
      AppState.isScreenCaptureExemptFromPaywall,
      "cloud-assist on sends screenshots to Omi's Gemini proxy again, so this must be metered")
  }

  // MARK: - Chat accounting (ChatRunAccountingPolicy)

  func testChatAccountingSkipsOmiQuotaForLocalProvider() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    let policy = ChatRunAccountingPolicy(pinnedAdapterID: AgentAdapterId.piMono.rawValue)
    XCTAssertFalse(
      policy.usesOmiAccountQuota,
      "Local shares piMono's harness but must never touch Omi's account quota/accounting")
  }

  /// Regression: the Omi-billed "omi" provider (still piMono) must keep
  /// touching quota/accounting exactly as before.
  func testChatAccountingUsesOmiQuotaForOmiProvider() {
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    let policy = ChatRunAccountingPolicy(pinnedAdapterID: AgentAdapterId.piMono.rawValue)
    XCTAssertTrue(policy.usesOmiAccountQuota)
  }

  // MARK: - Push-to-talk

  /// This gate (`FloatingBarUsageLimiter`) is independent of the trial-expired
  /// flag `desktop_isPaywalled` — it is left unset here, matching the actual
  /// bug: a user well within their trial can still exhaust the monthly
  /// question quota. PTT is exempt on `isLocalProviderActive` alone: the
  /// quota it enforces meters chat *questions*, and the completion a PTT turn
  /// feeds always runs against the user's own server under Local regardless
  /// of whether a self-hosted backend is configured for voice.
  func testPushToTalkExemptWhenLocalProviderHasSelfHostedBackendConfigured() throws {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)
    FloatingBarUsageLimiter.shared.applyQuota(try exhaustedFreeQuota())

    XCTAssertFalse(
      PushToTalkManager.shared.isPushToTalkUsageLimitBlocked,
      "voice capture is local too once a self-hosted backend URL is configured, "
        + "so PTT must not be blocked by the exhausted free-tier quota")
  }

  /// Local without a self-hosted backend still must not block PTT: the
  /// question-quota this gate enforces is orthogonal to whether voice
  /// transcription itself is local — that is `isTranscriptionExemptFromPaywall`'s
  /// job, checked separately at transcription start. A chat completion fed by
  /// PTT always runs against the user's own server under Local.
  func testPushToTalkExemptForLocalProviderWithoutSelfHostedBackend() throws {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.localBackendURLKey)
    FloatingBarUsageLimiter.shared.applyQuota(try exhaustedFreeQuota())

    XCTAssertFalse(
      PushToTalkManager.shared.isPushToTalkUsageLimitBlocked,
      "the owner runs Local with no self-hosted backend URL configured at all — that must "
        + "be a first-class configuration, and PTT's question quota does not apply to it")
  }

  /// Regression: the Omi provider is unaffected by this change.
  func testPushToTalkStaysGatedForOmiProvider() throws {
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    FloatingBarUsageLimiter.shared.applyQuota(try exhaustedFreeQuota())

    XCTAssertTrue(PushToTalkManager.shared.isPushToTalkUsageLimitBlocked)
  }

  // MARK: - Cloud-assisted features (single unified Local-provider setting;
  // connector synthesis is one of several features it now gates)

  func testConnectorSynthesisSkippedWhenLocalAndOff() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)
    XCTAssertTrue(AIProvider.shouldSkipConnectorSynthesis())
    XCTAssertFalse(AIProvider.localCloudAssistEnabled)
  }

  func testConnectorSynthesisNotSkippedWhenLocalAndCloudOptIn() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.cloud.rawValue, forKey: AIProvider.cloudAssistModeKey)
    XCTAssertFalse(
      AIProvider.shouldSkipConnectorSynthesis(),
      "opting into cloud-assisted features must still reach Omi's backend, which enforces its own gate")
    XCTAssertTrue(AIProvider.localCloudAssistEnabled)
  }

  func testConnectorSynthesisNotSkippedForOmiProviderRegardlessOfSetting() {
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)
    XCTAssertFalse(AIProvider.shouldSkipConnectorSynthesis())
    XCTAssertFalse(
      AIProvider.localCloudAssistEnabled,
      "the setting is meaningless off Local, and must never read as enabled for another provider")
  }

  /// Migration: an existing pre-unification connector-synthesis choice
  /// (`localConnectorSynthesisMode`) must carry forward to the new unified
  /// key the first time it is read, so a user who had already opted into
  /// cloud connector synthesis is not silently reset to Off by this rename.
  func testCloudAssistModeMigratesExistingCloudChoiceFromLegacyConnectorKey() {
    UserDefaults.standard.removeObject(forKey: AIProvider.cloudAssistModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.cloud.rawValue, forKey: AIProvider.connectorSynthesisModeKey)

    XCTAssertEqual(AIProvider.localCloudAssistMode, .cloud)
    XCTAssertEqual(
      UserDefaults.standard.string(forKey: AIProvider.cloudAssistModeKey),
      AIProvider.CloudAssistMode.cloud.rawValue,
      "the migrated value must be persisted under the new key, not just returned once")
  }

  /// An existing explicit Off under the legacy key must stay Off after
  /// migration — the exact regression this key rename must not introduce.
  func testCloudAssistModeMigratesExistingOffChoiceFromLegacyConnectorKey() {
    UserDefaults.standard.removeObject(forKey: AIProvider.cloudAssistModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.connectorSynthesisModeKey)

    XCTAssertEqual(AIProvider.localCloudAssistMode, .off)
  }

  /// A never-configured legacy key (fresh install, or a user who never
  /// touched the old connector-synthesis toggle) must resolve to the new
  /// setting's own default, not fail to migrate.
  func testCloudAssistModeDefaultsToOffWithNoLegacyKeyPresent() {
    UserDefaults.standard.removeObject(forKey: AIProvider.cloudAssistModeKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.connectorSynthesisModeKey)

    XCTAssertEqual(AIProvider.localCloudAssistMode, .off)
  }

  // MARK: - Cloud-assisted features: fail-closed gates

  /// `GeminiClient` is the shared entry point for every proactive assistant
  /// (task/memory/insight/suggestion extraction, goals, dictation polish).
  /// Under Local with cloud-assist off, it must throw before
  /// `ManagedProactivityDecisionSource.current()` is even consulted — that
  /// call can itself issue a subscription-refresh network request, so the
  /// gate must sit strictly before it, not just before the eventual HTTP call.
  func testGeminiClientEnforceManagedProactivityThrowsLocalProviderCloudOffBeforeAnyNetworkCall() async {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)
    // No override installed: if the gate did not fire first, this would fall
    // through to a real `SubscriptionEntitlementService` network call.
    do {
      try await GeminiClient.enforceManagedProactivity()
      XCTFail("expected localProviderCloudOff")
    } catch let error as GeminiClient.GeminiClientError {
      guard case .localProviderCloudOff = error else {
        return XCTFail("expected localProviderCloudOff, got \(error)")
      }
      XCTAssertFalse(error.shouldAutoRetry)
      XCTAssertFalse(error.isTransient)
      XCTAssertTrue(error.isExpectedProductState)
    } catch {
      XCTFail("expected GeminiClientError, got \(error)")
    }
  }

  /// Regression: opting cloud-assist on must let the call proceed to the
  /// normal entitlement check exactly as before. Pins a decision so this
  /// never depends on a real network call.
  func testGeminiClientEnforceManagedProactivityProceedsWhenLocalCloudAssistOn() async throws {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.cloud.rawValue, forKey: AIProvider.cloudAssistModeKey)
    ManagedProactivityDecisionSource.setOverride { .allowManagedProactivity }

    try await GeminiClient.enforceManagedProactivity()
  }

  /// `ProactiveLaneClient.complete()` is the context-director's own model
  /// call (task/insight/suggestion/resurface decisions from screen and
  /// transcript content) and must fail closed unconditionally — unlike its
  /// pre-existing pixel-only plan gate, this applies to text-only prompts too.
  func testProactiveLaneClientCompleteThrowsLocalProviderCloudOffForTextOnlyPrompt() async {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)
    let client = ProactiveLaneClient()
    do {
      _ = try await client.complete(
        operation: "test_operation",
        prompt: "text-only prompt, no image",
        jsonSchema: ["type": "object"])
      XCTFail("expected localProviderCloudOff")
    } catch let error as ProactiveLaneClientError {
      guard case .localProviderCloudOff = error else {
        return XCTFail("expected localProviderCloudOff, got \(error)")
      }
    } catch {
      XCTFail("expected ProactiveLaneClientError, got \(error)")
    }
  }

  /// `EmbeddingService` backs Rewind semantic search and task-similarity
  /// search. Under Local with cloud-assist off, both `embed` and `embedBatch`
  /// must fail before any network call so no screenshot or transcript text
  /// is ever sent for embedding.
  func testEmbeddingServiceEmbedThrowsLocalProviderCloudOffWhenLocalAndCloudAssistOff() async {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)
    do {
      _ = try await EmbeddingService.shared.embed(text: "a screenshot's OCR text")
      XCTFail("expected localProviderCloudOff")
    } catch let error as EmbeddingService.EmbeddingError {
      guard case .localProviderCloudOff = error else {
        return XCTFail("expected localProviderCloudOff, got \(error)")
      }
      XCTAssertTrue(
        error.isExpectedBackendState,
        "Rewind's existing 402-handling catch clauses key off this to degrade quietly")
    } catch {
      XCTFail("expected EmbeddingError, got \(error)")
    }
  }

  func testEmbeddingServiceEmbedBatchThrowsLocalProviderCloudOffWhenLocalAndCloudAssistOff() async {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)
    do {
      _ = try await EmbeddingService.shared.embedBatch(texts: ["one", "two"])
      XCTFail("expected localProviderCloudOff")
    } catch let error as EmbeddingService.EmbeddingError {
      guard case .localProviderCloudOff = error else {
        return XCTFail("expected localProviderCloudOff, got \(error)")
      }
    } catch {
      XCTFail("expected EmbeddingError, got \(error)")
    }
  }

  /// Regression: cloud-assist on must let embedding proceed to its normal
  /// network path (which will fail here for lack of a real proxy URL/auth —
  /// the point is only that it is NOT the `localProviderCloudOff` gate).
  func testEmbeddingServiceEmbedProceedsPastLocalGateWhenCloudAssistOn() async {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.cloud.rawValue, forKey: AIProvider.cloudAssistModeKey)
    do {
      _ = try await EmbeddingService.shared.embed(text: "test")
      // A real proxy call could conceivably succeed in some environments; either
      // outcome is fine as long as it is not the local-provider gate below.
    } catch let error as EmbeddingService.EmbeddingError {
      if case .localProviderCloudOff = error {
        XCTFail("cloud-assist on must not hit the Local-provider gate")
      }
    } catch {
      // Any other failure (network, auth) is expected in a unit test environment.
    }
  }

  /// `ChatToolExecutor`'s `web_search` tool always calls Omi's backend and
  /// must fail closed with a clear, quiet tool result rather than throwing or
  /// silently doing nothing under Local with cloud-assist off.
  func testWebSearchToolReturnsOffMessageWhenLocalAndCloudAssistOff() async {
    NegativeFeedbackRemediationFeature.testOverride = true
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)
    let ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture.establish(authOwnerID: "local-web-search-owner")

    let result = await ChatToolExecutor.execute(
      ToolCall(name: "web_search", arguments: ["query": "coffee shops nearby"], thoughtSignature: nil),
      expectedOwnerID: "local-web-search-owner",
      backendAPIClient: APIClient())

    XCTAssertEqual(
      result, "Web search is off under the Local provider (Settings > AI Provider > Cloud-assisted features)")
    await ownerFixture.restore()
  }

  // MARK: - Launch-time race: predicate must not depend on the async model fetch

  /// `isLocalProviderWithSelfHostedBackend`/`isLocalProviderActive` must read
  /// true the instant `chatBridgeMode` and `localBackendURL` are persisted
  /// (both plain synchronous `UserDefaults` strings), not after Settings'
  /// async `{baseURL}/models` fetch resolves and picks a first
  /// `localLLMModelID`. A fresh launch with a configured local base URL but
  /// no model id yet (the fetch still in flight) must already be exempt.
  /// This pins that no site can key its exemption off `localLLMModelID`
  /// instead and reintroduce a launch-time window where a Local session is
  /// wrongly paywalled.
  func testHasLocalBackendConfiguredTrueBeforeModelIdIsEverFetched() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.localModelIDKey)

    XCTAssertTrue(AIProvider.isLocalProviderActive)
    XCTAssertTrue(
      AIProvider.isLocalProviderWithSelfHostedBackend,
      "the exemption predicate must not require a model id the async fetch hasn't set yet")
  }

  /// Parallel-review regression (paywall-review.md item 5): a self-hosted
  /// backend URL left over from a prior Local session must not exempt an
  /// active Omi/cloud session just because the URL string is still
  /// persisted. `isLocalProviderWithSelfHostedBackend` always chains through
  /// `isLocalProviderActive` first — pin that here so a future edit cannot
  /// drop that clause without a test failing.
  func testLocalProviderWithSelfHostedBackendFalseWhenConfiguredButOmiProviderActive() {
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)

    XCTAssertFalse(AIProvider.isLocalProviderActive)
    XCTAssertFalse(
      AIProvider.isLocalProviderWithSelfHostedBackend,
      "a configured backend URL must not exempt a session where Local isn't even the active provider")
  }

  // MARK: - Central choke point: AppState.triggerUsageLimitPopup

  /// The reason family this file's central check covers. A cached
  /// `desktop_isPaywalled` flag left over from before the user switched to
  /// Local (or before they configured a self-hosted backend) must not raise
  /// the popup once Local is active with that backend configured. This is
  /// the single choke point every `.showUsageLimitPopup` poster funnels
  /// through (directly or via DesktopHomeView's notification listener).
  /// "transcription" is the reason `SystemCaptureControls.setAudioRecording`
  /// actually posts now (not "trial_expired" — see the regression test below).
  func testTriggerUsageLimitPopupSuppressedForTranscriptionWhenLocalBackendConfiguredEvenWithCachedTrialExpiredFlag() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)

    let state = AppState()
    state.triggerUsageLimitPopup(reason: "transcription")

    XCTAssertFalse(
      state.showUsageLimitPopup,
      "a stale cached trial_expired flag must not raise the transcription popup once "
        + "Local has a self-hosted backend")
  }

  /// Regression: "trial_expired" no longer has a Local-specific poster (both
  /// `SystemCaptureControls` gates now post their own narrower reason), and
  /// must not get a free pass here just because Local happens to be active —
  /// it names genuine Omi-account trial state, which Local does not change.
  func testTriggerUsageLimitPopupStaysForTrialExpiredReasonEvenWithLocalBackendConfigured() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)

    let state = AppState()
    state.triggerUsageLimitPopup(reason: "trial_expired")

    XCTAssertTrue(
      state.showUsageLimitPopup,
      "trial_expired must not be silently exempted just because Local is active")
  }

  /// "chat" and "ptt" are exempt on `isLocalProviderActive` alone — no
  /// self-hosted backend required, since the completion they feed always
  /// runs against the user's own server under Local.
  func testTriggerUsageLimitPopupSuppressedForChatWhenLocalActiveWithoutBackendConfigured() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.localBackendURLKey)

    let state = AppState()
    state.triggerUsageLimitPopup(reason: "chat")

    XCTAssertFalse(
      state.showUsageLimitPopup,
      "chat must be exempt under Local even with no self-hosted backend configured at all")
  }

  /// "screen_capture" mirrors `isScreenCaptureExemptFromPaywall` exactly: off
  /// (suppressed) while cloud-assist is off, back on (shown) once the user
  /// opts cloud-assisted features on and screen-capture-driven proactive
  /// features are metered again.
  func testTriggerUsageLimitPopupSuppressedForScreenCaptureWhenLocalAndCloudAssistOff() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.off.rawValue, forKey: AIProvider.cloudAssistModeKey)

    let state = AppState()
    state.triggerUsageLimitPopup(reason: "screen_capture")

    XCTAssertFalse(state.showUsageLimitPopup)
  }

  func testTriggerUsageLimitPopupStaysForScreenCaptureWhenLocalAndCloudAssistOn() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.CloudAssistMode.cloud.rawValue, forKey: AIProvider.cloudAssistModeKey)

    let state = AppState()
    state.triggerUsageLimitPopup(reason: "screen_capture")

    XCTAssertTrue(
      state.showUsageLimitPopup,
      "cloud-assist on re-meters screen-capture-driven proactive features like any cloud user")
  }

  /// Regression: the realtime-transcription-PROVIDER quota (Deepgram/Soniox
  /// exhaustion, `RealtimeHubController+SessionDelegate`) is a distinct axis
  /// from the AI chat provider and must keep surfacing even when Local chat
  /// is active with a self-hosted backend configured. This central check
  /// must never swallow it.
  func testTriggerUsageLimitPopupStaysForRealtimeReasonEvenWithLocalBackendConfigured() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)

    let state = AppState()
    state.triggerUsageLimitPopup(reason: "realtime")

    XCTAssertTrue(
      state.showUsageLimitPopup,
      "realtime STT-provider quota exhaustion is independent of the AI chat provider")
  }

  /// Regression: the Omi-billed provider keeps the popup exactly as before.
  func testTriggerUsageLimitPopupStaysForOmiProviderWithCachedTrialExpiredFlag() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)

    let state = AppState()
    state.triggerUsageLimitPopup(reason: "trial_expired")

    XCTAssertTrue(state.showUsageLimitPopup)
  }

  // MARK: - freemium_threshold_reached (AppState+ListenEvents)

  /// This server-pushed event used to check only transcription BYOK before
  /// hard-stopping capture and setting the sticky `isPaywalled` flag. It must
  /// also stand down once Local has a self-hosted backend configured. Voice
  /// no longer runs through Omi's Deepgram proxy at all in that state, so a
  /// stale/cached event must not stop transcription or raise the popup.
  func testFreemiumThresholdEventIgnoredWhenLocalBackendConfigured() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)

    let state = AppState()
    state.isPaywalled = false
    state.handleListenEvent(
      TranscriptionService.ListenEvent(
        type: "freemium_threshold_reached",
        raw: ["remaining_seconds": 0]))

    XCTAssertFalse(
      state.isPaywalled,
      "Local with a self-hosted backend must not be hard-stopped by a freemium threshold event")
    XCTAssertFalse(state.showUsageLimitPopup)
  }

  // MARK: - Tool-call quota during a Local turn degrades gracefully

  /// A backend 402 on a JIT/RAG tool call (memories, conversations, etc.)
  /// made mid-turn must not fail or block the whole Local chat turn. It must
  /// degrade to a tool-result error string the model can see and continue
  /// past. `ChatToolExecutor.execute` is `async -> String` and never throws,
  /// so completing at all is part of the proof; the rest pins the exact
  /// degraded shape (`ok:false`, a stable error code) rather than a crash or
  /// an unhandled/raw transport string reaching the model.
  func testSearchMemoriesToolDegradesGracefullyOnBackendQuotaErrorDuringLocalTurn() async throws {
    FixedStatusURLCapture.reset(statusCode: 402)
    setenv("OMI_PYTHON_API_URL", "http://local-turn-tool-quota-test:9001", 1)
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    let ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture.establish(authOwnerID: "local-turn-tool-owner")
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      FixedStatusURLCapture.reset(statusCode: 402)
    }

    do {
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [FixedStatusURLCapture.self]
      let client = APIClient(session: URLSession(configuration: configuration))
      await client.setTestAuthHeader("Bearer local-turn-tool-owner-token")

      let result = await ChatToolExecutor.execute(
        ToolCall(name: "search_memories", arguments: ["query": "coffee"], thoughtSignature: nil),
        expectedOwnerID: "local-turn-tool-owner",
        backendAPIClient: client)

      XCTAssertEqual(FixedStatusURLCapture.requestCount, 1)
      let payload = try XCTUnwrap(
        try JSONSerialization.jsonObject(with: XCTUnwrap(result.data(using: .utf8))) as? [String: Any],
        "the degraded result must still be well-formed JSON the tool-result relay can parse: \(result)")
      XCTAssertEqual(payload["ok"] as? Bool, false)
      let error = try XCTUnwrap(payload["error"] as? [String: Any])
      XCTAssertEqual(error["code"] as? String, "backend_tool_unreachable")
    } catch {
      await ownerFixture.restore()
      UserDefaults.standard.removeObject(forKey: bridgeModeKey)
      throw error
    }
    await ownerFixture.restore()
    UserDefaults.standard.removeObject(forKey: bridgeModeKey)
  }
}
