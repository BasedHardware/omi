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
  /// INV-INT-1: Apple Notes "Connected" must be the answer of a live access
  /// probe, never a stored timestamp or a one-time-success latch. The same
  /// persisted import history therefore has to read as connected or not
  /// connected purely on what the probe says right now.
  func testAppleNotesConnectedStateFollowsTheLiveProbeNotPersistedHistory() async {
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
    let syncedAt = Date(timeIntervalSince1970: 1_700_000_000)
    let readable = ImportConnectorStatusStore(
      defaults: defaults,
      sessionUserID: "test-user",
      appleNotesProbe: { .connected(noteCount: 834, verifiedAt: syncedAt) }
    )
    readable.markSynced(connectorID: connector.id, sourceCount: 3, syncedAt: syncedAt)

    await readable.refresh()

    let connected = readable.snapshot(for: connector)
    XCTAssertTrue(connected.isConnected)
    XCTAssertEqual(connected.actionTitle, "Sync now")
    XCTAssertEqual(connected.primaryText, "3 notes")

    // Same persisted history, revoked Automation access.
    let revoked = ImportConnectorStatusStore(
      defaults: defaults,
      sessionUserID: "test-user",
      appleNotesProbe: {
        .needsAccess(message: "Allow Omi to control Notes.", reasonCode: "automation_permission_denied")
      }
    )

    await revoked.refresh()

    let snapshot = revoked.snapshot(for: connector)
    XCTAssertFalse(snapshot.isConnected)
    XCTAssertEqual(snapshot.actionTitle, "Connect")
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
