import XCTest

@testable import Omi_Computer

final class DesktopReviewClaudeAuthRegressionTests: XCTestCase {
  func testExplicitClaudeOAuthSuccessSurvivesPassiveStatusRefresh() {
    XCTAssertFalse(
      ChatProvider.claudeConnectionStatus(configToken: nil, explicitAuthSucceeded: false)
    )
    XCTAssertTrue(
      ChatProvider.claudeConnectionStatus(configToken: nil, explicitAuthSucceeded: true)
    )
    XCTAssertTrue(
      ChatProvider.claudeConnectionStatus(configToken: "legacy-token", explicitAuthSucceeded: false)
    )
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
