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
}
