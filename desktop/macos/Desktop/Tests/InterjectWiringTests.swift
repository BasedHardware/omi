import XCTest

@testable import Omi_Computer

/// Seam tests for the paths the first Interject PR left unwired. Helpers can
/// stay green while hold-⌥ on a context-director card writes nothing.
final class InterjectWiringTests: XCTestCase {
  private let ownerID = "interject-wiring-owner"

  @MainActor
  func testContextDirectorCardReachesTheSingleMutationOwner() async throws {
    try await withInterjectHarness {
      let deliveryID = try XCTUnwrap(UUID(uuidString: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
      let cardID = try XCTUnwrap(UUID(uuidString: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
      let context = FloatingBarNotificationContext(
        sourceTitle: "Wrong insight",
        assistantId: "context-director",
        provenanceRef: deliveryID.uuidString
      )
      let card = FloatingBarNotification(
        ownerID: ownerID,
        title: "Thursday standup",
        message: "You have standup in 10 minutes",
        assistantId: "context-director",
        kind: .insight,
        context: context
      )
      XCTAssertNil(card.suggestionTelemetryIdentity)
      XCTAssertEqual(card.feedbackIdentity.evaluationID, deliveryID)
      XCTAssertEqual(card.feedbackIdentity.suggestionID, card.id)

      FloatingControlBarManager.shared.seedInterjectRecentCardForTests(
        ownerID: ownerID,
        title: card.title,
        createdAt: Date(),
        context: context,
        identity: nil,
        notificationID: cardID
      )

      await FloatingControlBarManager.shared.consumeInterjectVoiceReplyAsync(
        "[[interject:useful]] Got it — I'll keep surfacing that.")

      let record = await InterjectSuggestionFeedbackStore.shared.current(
        evaluationID: deliveryID, suggestionID: cardID)
      XCTAssertEqual(record?.verb, .useful)
    }
  }

  @MainActor
  func testHubTranscriptPathWritesTheSameLedger() async throws {
    try await withInterjectHarness {
      let deliveryID = try XCTUnwrap(UUID(uuidString: "cccccccc-cccc-cccc-cccc-cccccccccccc"))
      let cardID = try XCTUnwrap(UUID(uuidString: "dddddddd-dddd-dddd-dddd-dddddddddddd"))
      let context = FloatingBarNotificationContext(
        sourceTitle: "Task",
        assistantId: "context-director",
        provenanceRef: deliveryID.uuidString
      )
      FloatingControlBarManager.shared.seedInterjectRecentCardForTests(
        ownerID: ownerID,
        title: "Call Sam",
        createdAt: Date(),
        context: context,
        identity: nil,
        notificationID: cardID
      )

      await FloatingControlBarManager.shared.consumeInterjectHubTranscript(
        "[[interject:false_positive]] Okay — I won't nudge you about that.")

      let record = await InterjectSuggestionFeedbackStore.shared.current(
        evaluationID: deliveryID, suggestionID: cardID)
      XCTAssertEqual(record?.verb, .falsePositive)

      let journal = try sourceFile(
        "Sources/FloatingControlBar/FloatingControlBarManager+RealtimeStreamingJournal.swift")
      XCTAssertTrue(
        journal.contains("consumeInterjectHubTranscript(assistantText)"),
        "hub journal finalization must call the Interject seam, not only the batch path")
    }
  }

  func testLockedAndButtonPTTArmTheInterjectHold() throws {
    let ptt = try sourceFile("Sources/FloatingControlBar/PushToTalkManager.swift")
    XCTAssertTrue(
      ptt.contains("FloatingControlBarManager.shared.interjectPushToTalkDidStart()"),
      "hold-to-talk must still arm Interject")
    XCTAssertTrue(
      ptt.contains("enterLockedListening()"),
      "locked listening is the button / double-tap path")
    XCTAssertTrue(
      ptt.contains("stopListening(endInterjectHold: false)"),
      "tap-to-lock must not drop the hold before re-arming")

    let enterLocked = slice(
      ptt, startingAt: "func enterLockedListening()", endingBefore: "private func enterPendingLockDecision")
    XCTAssertTrue(
      enterLocked.contains("interjectPushToTalkDidStart()"),
      "button and double-tap lock must arm the hold so the card does not dismiss mid-turn")
  }

  @MainActor
  func testProvenanceRefCardUsesSixtySecondChipAndClassificationWindow() throws {
    try withInterjectHarness {
      let now = Date()
      let context = FloatingBarNotificationContext(
        sourceTitle: "Old director card",
        assistantId: "context-director",
        provenanceRef: "delivery-from-weeks-ago"
      )

      FloatingControlBarManager.shared.seedInterjectRecentCardForTests(
        ownerID: ownerID,
        title: "Weeks-old insight",
        createdAt: now.addingTimeInterval(-61),
        context: context,
        identity: nil
      )
      XCTAssertNil(
        FloatingControlBarManager.shared.recentNotchCardTitle(),
        "chip must not use the 30-day durable interval")
      XCTAssertNil(FloatingControlBarManager.shared.recentNotchCardFeedbackIdentity())
      XCTAssertFalse(
        FloatingControlBarManager.shared.shouldAttachInterjectClassification(now: now))

      FloatingControlBarManager.shared.seedInterjectRecentCardForTests(
        ownerID: ownerID,
        title: "Fresh insight",
        createdAt: now.addingTimeInterval(-10),
        context: context,
        identity: nil
      )
      XCTAssertEqual(FloatingControlBarManager.shared.recentNotchCardTitle(), "Fresh insight")
      XCTAssertNotNil(FloatingControlBarManager.shared.recentNotchCardFeedbackIdentity())
      XCTAssertTrue(
        FloatingControlBarManager.shared.shouldAttachInterjectClassification(now: now))
      XCTAssertEqual(InterjectReplyWindow.duration, 60)
    }
  }

  @MainActor
  func testPushToTalkStartArmsHoldOnTheManager() throws {
    try withInterjectHarness {
      let now = Date()
      FloatingControlBarManager.shared.seedInterjectRecentCardForTests(
        ownerID: ownerID,
        title: "Live card",
        createdAt: now,
        context: FloatingBarNotificationContext(
          sourceTitle: "Live card",
          assistantId: "context-director",
          provenanceRef: UUID().uuidString),
        identity: nil
      )
      XCTAssertFalse(FloatingControlBarManager.shared.interjectPTTHoldActiveForTests)
      FloatingControlBarManager.shared.interjectPushToTalkDidStart()
      XCTAssertTrue(
        FloatingControlBarManager.shared.interjectPTTHoldActiveForTests,
        "PTT start — including the locked path that calls this — must hold the card")
      FloatingControlBarManager.shared.interjectPushToTalkDidEnd()
      XCTAssertFalse(FloatingControlBarManager.shared.interjectPTTHoldActiveForTests)
    }
  }

  func testContextDirectorFeedbackIdentityDoesNotNeedSuggestionTelemetry() {
    let delivery = UUID()
    let card = FloatingBarNotification(
      ownerID: ownerID,
      title: "Insight",
      message: "Body",
      assistantId: "context-director",
      context: FloatingBarNotificationContext(
        sourceTitle: "Insight",
        assistantId: "context-director",
        provenanceRef: delivery.uuidString)
    )
    XCTAssertEqual(card.feedbackIdentity.evaluationID, delivery)
    XCTAssertEqual(JITTriggerFeedbackAction.useful.interjectVerb, .useful)
    XCTAssertEqual(JITTriggerFeedbackAction.missedOrLate.interjectVerb, .missed)
  }

  func testInsightTeaserKeysOffTheSameHoverSignalAsThePause() throws {
    let view = try sourceFile("Sources/FloatingControlBar/FloatingControlBarView.swift")
    let teaser = slice(
      view,
      startingAt: "func interjectInsightTeaserLimit",
      endingBefore: "private var aiInputView")
    XCTAssertTrue(
      teaser.contains("state.interjectBarHovering"),
      "teaser expansion must follow the pause signal, not notch isHoveringBar")
    XCTAssertFalse(
      teaser.contains("state.isHoveringBar"),
      "isHoveringBar is never set on the notch hover path")
  }

  @MainActor
  private func withInterjectHarness(_ body: () async throws -> Void) async throws {
    let defaults = UserDefaults.standard
    let previousOwner = defaults.object(forKey: .authUserId)
    let previousOverride = defaults.object(forKey: .automationOwnerOverride)
    defaults.removeObject(forKey: .automationOwnerOverride)
    defaults.set(ownerID, forKey: .authUserId)
    InterjectFeature.testOverride = true
    FloatingControlBarManager.shared.resetOwnerProjection()
    defer {
      FloatingControlBarManager.shared.resetOwnerProjection()
      InterjectFeature.testOverride = nil
      restore(previousOwner, key: .authUserId, defaults: defaults)
      restore(previousOverride, key: .automationOwnerOverride, defaults: defaults)
    }
    try await body()
    await InterjectSuggestionFeedbackStore.shared.removeAllForTests()
  }

  @MainActor
  private func withInterjectHarness(_ body: () throws -> Void) throws {
    let defaults = UserDefaults.standard
    let previousOwner = defaults.object(forKey: .authUserId)
    let previousOverride = defaults.object(forKey: .automationOwnerOverride)
    defaults.removeObject(forKey: .automationOwnerOverride)
    defaults.set(ownerID, forKey: .authUserId)
    InterjectFeature.testOverride = true
    FloatingControlBarManager.shared.resetOwnerProjection()
    defer {
      FloatingControlBarManager.shared.resetOwnerProjection()
      InterjectFeature.testOverride = nil
      restore(previousOwner, key: .authUserId, defaults: defaults)
      restore(previousOverride, key: .automationOwnerOverride, defaults: defaults)
    }
    try body()
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    // omi-test-quality: source-inspection -- static contract: hub journal and locked PTT must keep calling the Interject seams; behavioral coverage is in this file
    return try String(contentsOf: url, encoding: .utf8)
  }

  private func slice(_ source: String, startingAt: String, endingBefore: String) -> String {
    guard let start = source.range(of: startingAt),
      let end = source.range(of: endingBefore, range: start.upperBound..<source.endIndex)
    else { return "" }
    return String(source[start.lowerBound..<end.lowerBound])
  }

  private func restore(_ value: Any?, key: DefaultsKey, defaults: UserDefaults) {
    if let value {
      defaults.set(value, forKey: key)
    } else {
      defaults.removeObject(forKey: key)
    }
  }
}
