import XCTest

@testable import Omi_Computer

final class DesktopReviewClaudeAuthRegressionTests: XCTestCase {
  func testExplicitClaudeOAuthSuccessSurvivesPassiveStatusRefresh() {
    XCTAssertFalse(
      ChatProvider.claudeConnectionStatus(configToken: nil, explicitAuthSucceeded: false, providerRejected: false)
    )
    XCTAssertTrue(
      ChatProvider.claudeConnectionStatus(configToken: nil, explicitAuthSucceeded: true, providerRejected: false)
    )
    XCTAssertTrue(
      ChatProvider.claudeConnectionStatus(
        configToken: "legacy-token", explicitAuthSucceeded: false, providerRejected: false)
    )
  }

  func testAnObservedRejectionOutranksACachedTokenAndAnEarlierSuccess() {
    XCTAssertFalse(
      ChatProvider.claudeConnectionStatus(
        configToken: "legacy-token", explicitAuthSucceeded: true, providerRejected: true)
    )
  }
}

/// The real ChatProvider auth state, driven through the handlers the runtime's
/// `auth_required` / `auth_success` events call. No real config file or browser.
@MainActor
final class ClaudeProviderRejectionTests: XCTestCase {
  private let signInURL =
    "https://claude.ai/oauth/authorize?response_type=code&client_id=c&state=s1&code_challenge=x"
    + "&code_challenge_method=S256&redirect_uri=http%3A%2F%2Flocalhost%3A54545%2Fcallback"

  private func withUserClaude(_ body: (ChatProvider, () -> [URL]) -> Void) {
    let saved = UserDefaults.standard.string(forKey: .chatBridgeMode)
    defer {
      if let saved {
        UserDefaults.standard.set(saved, forKey: .chatBridgeMode)
      } else {
        UserDefaults.standard.removeObject(forKey: .chatBridgeMode)
      }
    }
    UserDefaults.standard.set(ChatProvider.BridgeMode.userClaude.rawValue, forKey: .chatBridgeMode)
    let provider = ChatProvider()
    var opened: [URL] = []
    provider.openClaudeSignInURL = { opened.append($0) }
    provider.readLegacyClaudeConfigToken = { "cached-token" }  // the old token is still on disk
    body(provider, { opened })
  }

  func testARejectedCredentialOffersConnectAndAPassiveRefreshCannotResurrectIt() {
    withUserClaude { provider, opened in
      provider.markClaudeAuthSucceeded()
      provider.checkClaudeConnectionStatus()
      XCTAssertTrue(provider.isClaudeConnected)

      provider.handleClaudeAuthRequired(methods: [], authUrl: nil)  // a chat turn was rejected
      // Both Settings surfaces render `claudeConnectionRow`, which offers Connect Claude
      // exactly when this is false.
      XCTAssertFalse(provider.isClaudeConnected)

      provider.checkClaudeConnectionStatus()
      XCTAssertFalse(provider.isClaudeConnected, "a cached token and the earlier success no longer count")
      XCTAssertTrue(opened().isEmpty, "a chat failure never opens the browser")
    }
  }

  func testAChatFailureCarryingASignInURLStillWaitsForConnect() {
    withUserClaude { provider, opened in
      provider.markClaudeAuthSucceeded()
      provider.handleClaudeAuthRequired(methods: [], authUrl: signInURL)
      XCTAssertFalse(provider.isClaudeConnected)
      XCTAssertTrue(opened().isEmpty)
      XCTAssertEqual(provider.claudeAuthUrl, signInURL, "the live flow is kept for an explicit Connect")
    }
  }

  func testExplicitReconnectRestoresConnectedOnlyAfterVerifiedSuccessAndCanRetry() {
    withUserClaude { provider, opened in
      provider.readLegacyClaudeConfigToken = { nil }  // the new token lives only in Keychain
      provider.handleClaudeAuthRequired(methods: [], authUrl: nil)

      provider.handleClaudeAuthRequired(methods: [], authUrl: signInURL)  // runtime answers Connect
      provider.startClaudeAuth()  // the explicit Connect path
      XCTAssertEqual(opened().map(\.absoluteString), [signInURL])
      provider.startClaudeAuth()
      XCTAssertEqual(opened().count, 1, "the same live callback flow is not opened twice")
      XCTAssertFalse(provider.isClaudeConnected, "opening the browser is not authentication")

      // The first attempt timed out; a retry gets a fresh flow and may open it.
      let retryURL = signInURL.replacingOccurrences(of: "state=s1", with: "state=s2")
      provider.handleClaudeAuthRequired(methods: [], authUrl: retryURL)
      provider.startClaudeAuth()
      XCTAssertEqual(opened().count, 2)

      provider.handleClaudeAuthSuccess()
      XCTAssertTrue(provider.isClaudeConnected)
      provider.checkClaudeConnectionStatus()
      XCTAssertTrue(provider.isClaudeConnected, "a verified sign-in survives passive refresh")
    }
  }
}

final class DesktopReviewPermissionRegressionTests: XCTestCase {
  func testStoppedSystemEventsPreservesTheLastKnownGrantAndReportsUnknown() {
    let granted = AppState.automationPermissionProjection(
      status: -600,
      previousPermission: true
    )
    XCTAssertTrue(granted.hasPermission)
    XCTAssertEqual(granted.error, -600)

    let unknown = AppState.automationPermissionProjection(
      status: -600,
      previousPermission: false
    )
    XCTAssertFalse(unknown.hasPermission)
    XCTAssertEqual(unknown.error, -600)
  }

  func testKnownAutomationStatusesStillProjectTheirExistingSemantics() {
    let allowed = AppState.automationPermissionProjection(status: noErr, previousPermission: false)
    XCTAssertTrue(allowed.hasPermission)
    XCTAssertEqual(allowed.error, 0)

    let denied = AppState.automationPermissionProjection(status: -1743, previousPermission: true)
    XCTAssertFalse(denied.hasPermission)
    XCTAssertEqual(denied.error, 0)
  }
}

@MainActor
final class DesktopReviewImportAndChatRegressionTests: XCTestCase {
  func testAppleNotesImportRequiresFreshVerificationAfterPassiveRefresh() async {
    let suiteName = "DesktopReviewImportAndChatRegressionTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("Expected an isolated user-defaults suite")
      return
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    guard let connector = ImportConnector.all.first(where: { $0.id == "apple-notes" }) else {
      XCTFail("Expected the Apple Notes import connector")
      return
    }
    let store = ImportConnectorStatusStore(defaults: defaults, sessionUserID: "test-user")
    store.markSynced(
      connectorID: connector.id,
      sourceCount: 3,
      syncedAt: Date(timeIntervalSince1970: 1_700_000_000)
    )
    XCTAssertTrue(store.snapshot(for: connector).isConnected)

    await store.refresh()

    let snapshot = store.snapshot(for: connector)
    XCTAssertFalse(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Connect")
    XCTAssertEqual(snapshot.primaryText, "Reconnect to verify access")
    XCTAssertTrue(snapshot.secondaryText?.hasPrefix("Last imported ") == true)
  }

  func testCompactTranscriptExpansionAnchorsToTheFirstVisibleRow() {
    let messages = (0..<120).map { index in
      ChatMessage(id: "message-\(index)", text: "Message \(index)", sender: .user)
    }
    let policy = ChatTranscriptWindow.Policy(initialMessageCount: 12, maximumMessageCount: 40)

    XCTAssertEqual(
      ChatTranscriptWindow.prependAnchorID(
        in: messages,
        policy: policy,
        presentation: .initial
      ),
      "message-108"
    )
    XCTAssertNotEqual(
      ChatTranscriptWindow.prependAnchorID(
        in: messages,
        policy: policy,
        presentation: .initial
      ),
      messages.first?.id
    )
  }
}
