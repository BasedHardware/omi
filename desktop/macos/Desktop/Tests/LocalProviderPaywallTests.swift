import XCTest

@testable import Omi_Computer

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
    for p in BYOKProvider.allCases {
      UserDefaults.standard.removeObject(forKey: p.storageKey)
    }
    UserDefaults.standard.removeObject(forKey: .byokLLMProvider)
    APIKeyService.persistEnrolledFingerprints([:])
    FloatingBarUsageLimiter.shared.reset()
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
  /// question quota.
  func testPushToTalkExemptWhenLocalProviderHasSelfHostedBackendConfigured() throws {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set("http://localhost:9999", forKey: AIProvider.localBackendURLKey)
    FloatingBarUsageLimiter.shared.applyQuota(try exhaustedFreeQuota())

    XCTAssertFalse(
      PushToTalkManager.shared.isPushToTalkUsageLimitBlocked,
      "voice capture is local too once a self-hosted backend URL is configured, "
        + "so PTT must not be blocked by the exhausted free-tier quota")
  }

  /// Regression: Local text alone, with no self-hosted backend for
  /// transcription, still sends the audio to Omi's Deepgram proxy — PTT must
  /// stay gated exactly as before.
  func testPushToTalkStaysGatedForLocalProviderWithoutSelfHostedBackend() throws {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.removeObject(forKey: AIProvider.localBackendURLKey)
    FloatingBarUsageLimiter.shared.applyQuota(try exhaustedFreeQuota())

    XCTAssertTrue(PushToTalkManager.shared.isPushToTalkUsageLimitBlocked)
  }

  /// Regression: the Omi provider is unaffected by this change.
  func testPushToTalkStaysGatedForOmiProvider() throws {
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    FloatingBarUsageLimiter.shared.applyQuota(try exhaustedFreeQuota())

    XCTAssertTrue(PushToTalkManager.shared.isPushToTalkUsageLimitBlocked)
  }

  // MARK: - Connector synthesis (unchanged; confirms the gate this fix must not touch)

  func testConnectorSynthesisSkippedWhenLocalAndOff() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.ConnectorSynthesisMode.off.rawValue, forKey: AIProvider.connectorSynthesisModeKey)
    XCTAssertTrue(AIProvider.shouldSkipConnectorSynthesis())
  }

  func testConnectorSynthesisNotSkippedWhenLocalAndCloudOptIn() {
    UserDefaults.standard.set("local", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.ConnectorSynthesisMode.cloud.rawValue, forKey: AIProvider.connectorSynthesisModeKey)
    XCTAssertFalse(
      AIProvider.shouldSkipConnectorSynthesis(),
      "opting into cloud synthesis must still reach Omi's backend, which enforces its own gate")
  }

  func testConnectorSynthesisNotSkippedForOmiProviderRegardlessOfSetting() {
    UserDefaults.standard.set("piMono", forKey: bridgeModeKey)
    UserDefaults.standard.set(
      AIProvider.ConnectorSynthesisMode.off.rawValue, forKey: AIProvider.connectorSynthesisModeKey)
    XCTAssertFalse(AIProvider.shouldSkipConnectorSynthesis())
  }
}
