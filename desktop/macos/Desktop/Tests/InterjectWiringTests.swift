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
    }
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

  @MainActor
  func testFinalizeOnTheManagerKeepsAnUnconfirmedInject() async throws {
    try await withInterjectHarness {
      var injected: [String] = []
      final class AcceptBox: @unchecked Sendable { var value = false }
      let accept = AcceptBox()
      var scheduled: [@MainActor () async -> Void] = []
      InterjectClassificationDelivery.shared.configureForTesting(
        isVoiceSessionLive: { true },
        injectInstruction: { text in
          guard accept.value else { return false }
          injected.append(text)
          return true
        },
        scheduleWork: { work in
          scheduled.append(work)
        }
      )
      defer { InterjectClassificationDelivery.shared.resetForTesting() }

      FloatingControlBarManager.shared.seedInterjectRecentCardForTests(
        ownerID: ownerID,
        title: "Live card",
        createdAt: Date(),
        context: FloatingBarNotificationContext(
          sourceTitle: "Live card",
          assistantId: "context-director",
          provenanceRef: UUID().uuidString),
        identity: nil
      )

      FloatingControlBarManager.shared.interjectPushToTalkDidStart()
      while !scheduled.isEmpty {
        let work = scheduled.removeFirst()
        await work()
      }
      XCTAssertNotNil(InterjectClassificationDelivery.shared.pendingInstruction)

      FloatingControlBarManager.shared.interjectPushToTalkDidEnd()
      XCTAssertFalse(FloatingControlBarManager.shared.interjectPTTHoldActiveForTests)
      XCTAssertNotNil(
        InterjectClassificationDelivery.shared.pendingInstruction,
        "finalize must keep the inject for this turn's input window")

      accept.value = true
      InterjectClassificationDelivery.shared.voiceSessionDidOpenInputWindow()
      while !scheduled.isEmpty {
        let work = scheduled.removeFirst()
        await work()
      }
      XCTAssertEqual(injected.count, 1)
      XCTAssertTrue(injected[0].contains("TURN INSTRUCTION"))
    }
  }

  @MainActor
  func testTapToLockOnTheManagerProducesExactlyOneInject() async throws {
    try await withInterjectHarness {
      var injected: [String] = []
      var scheduled: [@MainActor () async -> Void] = []
      InterjectClassificationDelivery.shared.configureForTesting(
        isVoiceSessionLive: { true },
        injectInstruction: { text in
          injected.append(text)
          return true
        },
        scheduleWork: { work in
          scheduled.append(work)
        }
      )
      defer { InterjectClassificationDelivery.shared.resetForTesting() }

      FloatingControlBarManager.shared.seedInterjectRecentCardForTests(
        ownerID: ownerID,
        title: "Live card",
        createdAt: Date(),
        context: FloatingBarNotificationContext(
          sourceTitle: "Live card",
          assistantId: "context-director",
          provenanceRef: UUID().uuidString),
        identity: nil
      )

      // startListening then enterLockedListening both call DidStart.
      FloatingControlBarManager.shared.interjectPushToTalkDidStart()
      FloatingControlBarManager.shared.interjectPushToTalkDidStart()
      while !scheduled.isEmpty {
        let work = scheduled.removeFirst()
        await work()
      }
      XCTAssertEqual(injected.count, 1, "tap-to-lock must not enqueue a second inject")
      XCTAssertTrue(injected[0].contains("TURN INSTRUCTION"))
    }
  }

  @MainActor
  func testFlagOffJITVerdictWritesNoLedgerAndEmitsNoAnalytics() async throws {
    try await withInterjectHarness {
      InterjectFeature.testOverride = false
      var events: [String] = []
      AnalyticsManager.shared.setSuggestionAssistantTelemetryCaptureForTests { event, _ in
        events.append(event)
      }
      defer { AnalyticsManager.shared.setSuggestionAssistantTelemetryCaptureForTests(nil) }

      let evaluation = try XCTUnwrap(UUID(uuidString: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))
      let suggestion = try XCTUnwrap(UUID(uuidString: "ffffffff-ffff-ffff-ffff-ffffffffffff"))
      await FloatingControlBarManager.shared.recordInterjectJITVerdictIfEnabled(
        identity: SuggestionAssistantTelemetry.NotificationIdentity(
          evaluationID: evaluation, suggestionID: suggestion),
        verb: .useful
      )

      let record = await InterjectSuggestionFeedbackStore.shared.current(
        evaluationID: evaluation, suggestionID: suggestion)
      XCTAssertNil(record, "flag-off JIT must not write the Interject store")
      XCTAssertFalse(
        events.contains("Suggestion Feedback Recorded"),
        "flag-off JIT must not emit Suggestion Feedback Recorded")
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

  @MainActor
  private func withInterjectHarness(_ body: () async throws -> Void) async throws {
    let defaults = UserDefaults.standard
    let previousOwner = defaults.object(forKey: .authUserId)
    let previousOverride = defaults.object(forKey: .automationOwnerOverride)
    defaults.removeObject(forKey: .automationOwnerOverride)
    defaults.set(ownerID, forKey: .authUserId)
    InterjectFeature.testOverride = true
    FloatingControlBarManager.shared.resetOwnerProjection()
    InterjectClassificationDelivery.shared.resetForTesting()
    defer {
      InterjectClassificationDelivery.shared.resetForTesting()
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
    InterjectClassificationDelivery.shared.resetForTesting()
    defer {
      InterjectClassificationDelivery.shared.resetForTesting()
      FloatingControlBarManager.shared.resetOwnerProjection()
      InterjectFeature.testOverride = nil
      restore(previousOwner, key: .authUserId, defaults: defaults)
      restore(previousOverride, key: .automationOwnerOverride, defaults: defaults)
    }
    try body()
  }

  private func restore(_ value: Any?, key: DefaultsKey, defaults: UserDefaults) {
    if let value {
      defaults.set(value, forKey: key)
    } else {
      defaults.removeObject(forKey: key)
    }
  }
}
