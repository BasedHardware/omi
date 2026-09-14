import XCTest

@testable import Omi_Computer

/// Verifies the BYOK-vs-paywall precedence fix: a user with a configured BYOK
/// key locally is never paywalled, regardless of the persisted
/// `desktop_isPaywalled` flag.
@MainActor final class BYOKPaywallTests: XCTestCase {
  private let paywallKey = "desktop_isPaywalled"

  private func setAllBYOKKeys() {
    for p in BYOKProvider.allCases {
      UserDefaults.standard.set("sk-test-\(p.rawValue)", forKey: p.storageKey)
    }
  }

  private func clearAllBYOKKeys() {
    for p in BYOKProvider.allCases {
      UserDefaults.standard.removeObject(forKey: p.storageKey)
    }
  }

  /// `isByokActive` requires the selected provider's *current* key to match a
  /// fingerprint already persisted by `activateBYOK` reconciliation — raw
  /// UserDefaults presence alone is not enough (#11454 replaced the old
  /// all-keys-present check with this enrollment contract). Tests that
  /// exercise `isByokActive`/`isPaywalledEffective` must enroll the provider
  /// whose key they just set, and re-enroll whenever that key's value changes.
  private func enroll(_ p: BYOKProvider) {
    guard let key = APIKeyService.byokKey(p) else {
      XCTFail("enroll(\(p)) called before \(p.storageKey) was set")
      return
    }
    APIKeyService.persistEnrolledFingerprints([p.rawValue: APIKeyService.byokFingerprint(key)])
  }

  override func tearDown() async throws {
    CredentialHealthManager.shared.reset()
    clearAllBYOKKeys()
    UserDefaults.standard.removeObject(forKey: paywallKey)
    UserDefaults.standard.removeObject(forKey: .byokLLMProvider)
    APIKeyService.persistEnrolledFingerprints([:])
  }

  func testByokActiveRequiresSelectedLLMKey() {
    clearAllBYOKKeys()
    XCTAssertFalse(APIKeyService.isByokActive)

    // A selected LLM key activates BYOK without the optional providers.
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    for p in BYOKProvider.allCases.dropLast() {
      UserDefaults.standard.set("k", forKey: p.storageKey)
    }
    enroll(.openrouter)
    XCTAssertTrue(APIKeyService.isByokActive)

    // All configured providers remain active. setAllBYOKKeys() rewrites
    // openrouter's key to "sk-test-openrouter", which invalidates the
    // fingerprint just enrolled above — re-enroll against the new value.
    setAllBYOKKeys()
    enroll(.openrouter)
    XCTAssertTrue(APIKeyService.isByokActive)
  }

  func testLegacyLLMSelectionInfersStoredProvider() {
    clearAllBYOKKeys()
    UserDefaults.standard.removeObject(forKey: .byokLLMProvider)
    UserDefaults.standard.set("sk-test-openai", forKey: BYOKProvider.openai.storageKey)

    XCTAssertEqual(APIKeyService.selectedBYOKLLMProvider, .openai)
  }

  func testBuildHeadersAttachSelectedLLMByokKey() async throws {
    clearAllBYOKKeys()
    UserDefaults.standard.set("sk-test-openai", forKey: BYOKProvider.openai.storageKey)
    enroll(.openai)

    let client = APIClient()
    await client.setTestAuthHeader("Bearer test-token")
    let headers = try await client.buildHeaders()

    XCTAssertEqual(headers[BYOKProvider.openai.headerName], "sk-test-openai")
  }

  func testBuildHeadersCanExplicitlyExcludeByokKeys() async throws {
    setAllBYOKKeys()

    let client = APIClient()
    await client.setTestAuthHeader("Bearer test-token")
    let headers = try await client.buildHeaders(includeBYOK: false)

    for provider in BYOKProvider.allCases {
      XCTAssertNil(headers[provider.headerName])
    }
  }

  func testLowLevelTransportDefaultsToExcludingByokKeys() async throws {
    setAllBYOKKeys()

    var transport = OmiHTTPTransport()
    transport.testAuthHeader = "Bearer test-token"
    let headers = try await transport.buildHeaders()

    for provider in BYOKProvider.allCases {
      XCTAssertNil(headers[provider.headerName])
    }
  }

  func testBuildHeadersSuppressesOnlyInvalidByokHeader() async throws {
    setAllBYOKKeys()
    UserDefaults.standard.set(BYOKLLMProvider.openai.rawValue, forKey: .byokLLMProvider)
    enroll(.openai)
    let openAIKey = try XCTUnwrap(APIKeyService.byokKey(.openai))
    CredentialHealthManager.shared.recordProviderFailure(
      .providerAuthFailed(provider: .openai, mode: .byok),
      provider: .openai,
      authMode: .byok,
      fingerprint: APIKeyService.byokFingerprint(openAIKey),
      context: "test")

    let client = APIClient()
    await client.setTestAuthHeader("Bearer test-token")
    let headers = try await client.buildHeaders()

    XCTAssertNil(headers[BYOKProvider.openai.headerName])
    XCTAssertEqual(headers[BYOKProvider.deepgram.headerName], "sk-test-deepgram")
    XCTAssertNil(headers[BYOKProvider.openrouter.headerName])
    XCTAssertNil(headers[BYOKProvider.anthropic.headerName])
    XCTAssertNil(headers[BYOKProvider.gemini.headerName])
  }

  func testPaywallFlagSuppressedWhenByokActive() {
    // The exact bug: trial-expired flag set, then user configures BYOK keys.
    UserDefaults.standard.set(true, forKey: paywallKey)
    setAllBYOKKeys()
    // Explicit provider selection: with every provider's key set, legacy
    // inference (first BYOKLLMProvider.allCases with a key present) would
    // silently pick whichever provider we did not enroll.
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    enroll(.openrouter)
    XCTAssertFalse(
      AppState.isPaywalledEffective,
      "BYOK-active user must NOT be paywalled even with the flag set")
  }

  func testPaywallFlagAppliesWhenNotByok() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    clearAllBYOKKeys()
    XCTAssertTrue(
      AppState.isPaywalledEffective,
      "Non-BYOK trial-expired user stays paywalled")
  }

  func testNotPaywalledWhenFlagUnset() {
    UserDefaults.standard.set(false, forKey: paywallKey)
    clearAllBYOKKeys()
    XCTAssertFalse(AppState.isPaywalledEffective)
  }

  func testRemovingDeepgramKeyLeavesSelectedLLMByokActive() {
    UserDefaults.standard.set(true, forKey: paywallKey)
    setAllBYOKKeys()
    // Explicit provider selection: with every provider's key set, legacy
    // inference (first BYOKLLMProvider.allCases with a key present) would
    // silently pick whichever provider we did not enroll.
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    enroll(.openrouter)
    XCTAssertFalse(AppState.isPaywalledEffective)

    // Deepgram is optional when a selected LLM key remains configured.
    UserDefaults.standard.removeObject(forKey: BYOKProvider.deepgram.storageKey)
    XCTAssertFalse(AppState.isPaywalledEffective)
  }

  func testHasTranscriptionBYOKRequiresEnrolledDeepgramFingerprint() {
    clearAllBYOKKeys()
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    UserDefaults.standard.set("sk-or", forKey: BYOKProvider.openrouter.storageKey)
    UserDefaults.standard.set("dg-rejected", forKey: BYOKProvider.deepgram.storageKey)
    APIKeyService.persistEnrolledFingerprints([:])

    XCTAssertFalse(
      APIKeyService.hasTranscriptionBYOK,
      "raw Deepgram presence must not suppress transcription exhaustion")

    let fp = APIKeyService.byokFingerprint("dg-rejected")
    APIKeyService.persistEnrolledFingerprints(["deepgram": fp])
    XCTAssertTrue(APIKeyService.hasTranscriptionBYOK)

    UserDefaults.standard.set("dg-rotated", forKey: BYOKProvider.deepgram.storageKey)
    XCTAssertFalse(
      APIKeyService.hasTranscriptionBYOK,
      "rotated Deepgram key is not enrolled until validation succeeds")
  }

  func testSelectedRealtimeBYOKKeyIgnoresUnselectedLeftover() {
    clearAllBYOKKeys()
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    UserDefaults.standard.set("sk-or", forKey: BYOKProvider.openrouter.storageKey)
    UserDefaults.standard.set("sk-openai-leftover", forKey: BYOKProvider.openai.storageKey)
    UserDefaults.standard.set("sk-gemini-leftover", forKey: BYOKProvider.gemini.storageKey)

    XCTAssertEqual(APIKeyService.selectedBYOKLLMProvider, .openrouter)
    XCTAssertNil(APIKeyService.selectedRealtimeBYOKKey(for: .openai))
    XCTAssertNil(APIKeyService.selectedRealtimeBYOKKey(for: .gemini))
    XCTAssertEqual(APIKeyService.selectedRealtimeBYOKKey(for: .openrouter), "sk-or")
  }

  /// The realtime hub speaks through OpenAI Realtime or Gemini Live and nothing else, so
  /// choosing one of those under Advanced → Voice Model is choosing that provider for
  /// voice. Withholding the key because the *text* provider is something the hub can
  /// never use — OpenRouter has no realtime API, and is the default — sent the turn to
  /// the managed lane, where it failed on Omi billing with the user's own key unspent.
  func testVoiceModelChoiceUnlocksItsOwnKeyWhileTextProviderDiffers() {
    clearAllBYOKKeys()
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    UserDefaults.standard.set("sk-or", forKey: BYOKProvider.openrouter.storageKey)
    UserDefaults.standard.set("sk-gemini-chosen", forKey: BYOKProvider.gemini.storageKey)

    XCTAssertEqual(APIKeyService.selectedBYOKLLMProvider, .openrouter)
    XCTAssertEqual(
      APIKeyService.selectedRealtimeBYOKKey(for: .gemini, chosenForVoice: true),
      "sk-gemini-chosen",
      "a provider chosen as the Voice Model must be able to use its own key")
  }

  /// The other direction, which is the whole reason the guard exists: the failover path
  /// does not pass `chosenForVoice`, so a key belonging to a provider the user picked
  /// nowhere is still never spent.
  func testFailoverStillRefusesAnUnchosenKey() {
    clearAllBYOKKeys()
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    UserDefaults.standard.set("sk-or", forKey: BYOKProvider.openrouter.storageKey)
    UserDefaults.standard.set("sk-openai-leftover", forKey: BYOKProvider.openai.storageKey)

    XCTAssertNil(
      APIKeyService.selectedRealtimeBYOKKey(for: .openai),
      "the failover must not spend a key the user chose neither for text nor for voice")
  }

  /// The two tests above pin `APIKeyService`'s boolean, but the boolean is only ever as
  /// good as what the call sites pass. The decision that actually separates primary from
  /// failover is the equality at the session call site: `effectiveProvider` is
  /// `fallbackProvider ?? RealtimeHubSettings.shared.provider`, so comparing against the
  /// settings value is what withholds the key from a provider reached by failover.
  /// Widening it to a blanket `true` would spend a leftover key on the failover path and
  /// still pass every behavioral test here, so the shape is pinned directly.
  func testTheSessionCallSiteDerivesVoiceChoiceFromTheVoiceModelSetting() throws {
    let source = try RealtimeHubControllerSourceTestSupport.moduleSource()

    XCTAssertTrue(
      source.contains("chosenForVoice: RealtimeHubSettings.shared.isVoiceModelChoice(provider)"),
      "the session call site must derive voice choice from the Voice Model setting, so a "
        + "provider reached by failover or by `.auto` is still refused the user's key")
    XCTAssertFalse(
      source.contains("chosenForVoice: true"),
      "no RealtimeHubController call site may claim voice choice unconditionally")
  }

  /// The E2E harness exists to drive the real path, so it has to make the same decision.
  /// Before this was aligned it called `selectedRealtimeBYOKKey(for:)` with no
  /// `chosenForVoice`, which meant that for exactly the configuration this fix addresses
  /// — Voice Model Gemini or OpenAI, text provider OpenRouter — the harness found no key
  /// and minted an ephemeral token, testing the managed lane instead of the fix.
  func testTheAutomationHarnessResolvesTheKeyThroughTheSameRule() throws {
    let source = try RealtimeHubControllerSourceTestSupport.source(
      named: "RealtimeHubTestHarness.swift")

    XCTAssertTrue(
      source.contains("chosenForVoice: RealtimeHubSettings.shared.isVoiceModelChoice(provider)"),
      "the harness must resolve BYOK auth the way a real session does")
  }

  /// `.auto` is the default Voice Model and resolves to Gemini, so treating "the hub is
  /// on Gemini" as "the user chose Gemini" would spend a stored Gemini key for every user
  /// who never opened the setting — a provider picked by a benchmark, not by them. Only an
  /// explicit selection counts; `.auto` keeps the stricter Developer-Keys-only rule.
  @MainActor
  func testAutoVoiceModelIsNotAVoiceChoice() {
    let previous = RealtimeOmniSettings.shared.selectedProvider
    defer { RealtimeOmniSettings.shared.selectedProvider = previous }

    RealtimeOmniSettings.shared.selectedProvider = .auto
    XCTAssertFalse(
      RealtimeHubSettings.shared.isVoiceModelChoice(RealtimeHubSettings.shared.provider),
      "`.auto` resolving to a provider is not the user choosing it")

    RealtimeOmniSettings.shared.selectedProvider = .geminiFlashLive
    XCTAssertTrue(
      RealtimeHubSettings.shared.isVoiceModelChoice(.gemini),
      "an explicit Voice Model selection is a choice")
    XCTAssertFalse(
      RealtimeHubSettings.shared.isVoiceModelChoice(.openai),
      "choosing one provider does not unlock the other's key")
  }
}
