import XCTest

@testable import Omi_Computer

final class PermissionRequestAuthorizationTests: XCTestCase {
  func testDirectNamedPermissionRequestIsSingleUse() {
    let authorization = PermissionRequestAuthorization.authorize(
      userMessage: "Open Screen Recording settings.",
      precedingAssistantMessage: nil,
      now: Date(timeIntervalSince1970: 1_000)
    )

    XCTAssertNotNil(authorization)
    XCTAssertTrue(authorization?.consume(permissionType: "screen_recording", now: Date(timeIntervalSince1970: 1_001)) == true)
    XCTAssertFalse(authorization?.consume(permissionType: "screen_recording", now: Date(timeIntervalSince1970: 1_001)) == true)
  }

  func testAffirmativeReplyUsesTheImmediatelyPrecedingPermissionRequest() {
    let authorization = PermissionRequestAuthorization.authorize(
      userMessage: "Yes",
      precedingAssistantMessage: "I need Screen Recording permission to take a screenshot. Say grant it and I will open Settings.",
      now: Date(timeIntervalSince1970: 1_000)
    )

    XCTAssertTrue(authorization?.consume(permissionType: "screen_recording", now: Date(timeIntervalSince1970: 1_001)) == true)
    XCTAssertFalse(authorization?.consume(permissionType: "microphone", now: Date(timeIntervalSince1970: 1_001)) == true)
  }

  func testGenericAndMultiPermissionRequestsDoNotAuthorizeASettingsOpen() {
    XCTAssertNil(
      PermissionRequestAuthorization.authorize(
        userMessage: "Grant permissions",
        precedingAssistantMessage: nil
      )
    )
    XCTAssertNil(
      PermissionRequestAuthorization.authorize(
        userMessage: "Please grant microphone and screen recording permissions.",
        precedingAssistantMessage: nil
      )
    )
  }

  func testRefusalsAndNonRequestsDoNotAuthorizeASettingsOpen() {
    for message in [
      "Please don't request microphone permission.",
      "Please explain microphone permission.",
      "Please open Comic Sans settings.",
    ] {
      XCTAssertNil(PermissionRequestAuthorization.authorize(userMessage: message, precedingAssistantMessage: nil))
    }
  }

  func testAuthorizationExpires() {
    let authorization = PermissionRequestAuthorization(
      permissions: [.microphone],
      expiresAt: Date(timeIntervalSince1970: 1_000)
    )

    XCTAssertFalse(authorization.consume(permissionType: "microphone", now: Date(timeIntervalSince1970: 1_001)))
  }

  func testPrimaryChatPassesCurrentTurnAuthorizationToTheToolExecutor() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Providers/ChatProvider.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("let isPrimaryChatPermissionSurface = systemPromptStyle == .main"))
    XCTAssertTrue(source.contains("let precedingAssistantMessage = messages.last.flatMap"))
    XCTAssertFalse(source.contains("messages.last(where: { $0.sender == .ai"))
    XCTAssertTrue(source.contains("PermissionRequestAuthorization.authorize("))
    XCTAssertTrue(source.contains("permissionAuthorization: permissionAuthorization"))
    XCTAssertTrue(source.contains("only after they explicitly request or affirm it"))
  }
}
