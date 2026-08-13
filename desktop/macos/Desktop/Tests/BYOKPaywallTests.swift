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

  override func tearDown() async throws {
    CredentialHealthManager.shared.reset()
    clearAllBYOKKeys()
    UserDefaults.standard.removeObject(forKey: paywallKey)
    UserDefaults.standard.removeObject(forKey: .byokLLMProvider)
  }

  func testByokActiveRequiresSelectedLLMKey() {
    clearAllBYOKKeys()
    XCTAssertFalse(APIKeyService.isByokActive)

    // A selected LLM key activates BYOK without the optional providers.
    UserDefaults.standard.set(BYOKLLMProvider.openrouter.rawValue, forKey: .byokLLMProvider)
    for p in BYOKProvider.allCases.dropLast() {
      UserDefaults.standard.set("k", forKey: p.storageKey)
    }
    XCTAssertTrue(APIKeyService.isByokActive)

    // All configured providers remain active.
    setAllBYOKKeys()
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
    XCTAssertFalse(AppState.isPaywalledEffective)

    // Deepgram is optional when a selected LLM key remains configured.
    UserDefaults.standard.removeObject(forKey: BYOKProvider.deepgram.storageKey)
    XCTAssertFalse(AppState.isPaywalledEffective)
  }
}
