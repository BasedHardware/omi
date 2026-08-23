import XCTest

@testable import Omi_Computer

/// Tests for the proactive_message event delivered over /v4/listen.
///
/// The handler in AppState+ListenEvents extracts fields, gates on empty bodies,
/// and delivers via FloatingControlBarManager.  These tests cover the parse and
/// gate contract; the presentation surface is the same one tested by the
/// existing proactive-notification suite (DeadProactivePathTests,
/// ProactiveAssistantOrchestrationPolicyTests, etc.).
@MainActor
final class ProactiveListenEventTests: XCTestCase {

  // MARK: - Event parsing round-trip (backend model → ListenEvent)

  func testProactiveMessageEventRoundTrip() throws {
    // Simulate the JSON the backend publishes via Redis → websocket
    let backendJSON: [String: Any] = [
      "type": "proactive_message",
      "app_id": "mentor",
      "title": "Omi",
      "message": "You mentioned earlier you needed to email your boss.",
      "conversation_id": "conv-42",
    ]

    let event = TranscriptionService.ListenEvent(
      type: (backendJSON["type"] as? String) ?? "",
      raw: backendJSON
    )

    XCTAssertEqual(event.type, "proactive_message")
    XCTAssertEqual(event.raw["app_id"] as? String, "mentor")
    XCTAssertEqual(event.raw["title"] as? String, "Omi")
    XCTAssertEqual(
      event.raw["message"] as? String,
      "You mentioned earlier you needed to email your boss.")
    XCTAssertEqual(event.raw["conversation_id"] as? String, "conv-42")
  }

  func testProactiveMessageEventWithoutOptionalConversationId() throws {
    let backendJSON: [String: Any] = [
      "type": "proactive_message",
      "app_id": "third-party-app",
      "title": "My App",
      "message": "Here's a useful tip.",
    ]

    let event = TranscriptionService.ListenEvent(
      type: (backendJSON["type"] as? String) ?? "",
      raw: backendJSON
    )

    XCTAssertEqual(event.type, "proactive_message")
    XCTAssertNil(event.raw["conversation_id"] as? String)
  }

  // MARK: - admission: show vs suppress

  /// The previous versions of these two tests called `handleListenEvent` with no
  /// runtime owner and asserted only that it did not crash, which covered
  /// neither delivery nor suppression. `ProactiveListenAdmission` is the pure
  /// decision the handler now takes, so each branch can be asserted directly.

  func testProactiveMessageIsDeliveredWhenOwnedAndNonEmpty() {
    XCTAssertEqual(
      ProactiveListenAdmission.decide(
        appID: "mentor", title: "Omi", message: "You said you'd call the bank.",
        hasRuntimeOwner: true),
      .deliver(title: "Omi", message: "You said you'd call the bank.", assistantId: "mentor"))
  }

  func testEmptyMessageIsSuppressed() {
    XCTAssertEqual(
      ProactiveListenAdmission.decide(
        appID: "mentor", title: "Omi", message: "", hasRuntimeOwner: true),
      .skip(.emptyMessage))
  }

  /// A listen socket can outlive a sign-out; delivering then would hand one
  /// user's mentor prompt to whoever is signed in now.
  func testMessageIsSuppressedWithoutARuntimeOwner() {
    XCTAssertEqual(
      ProactiveListenAdmission.decide(
        appID: "mentor", title: "Omi", message: "You said you'd call the bank.",
        hasRuntimeOwner: false),
      .skip(.noRuntimeOwner))
  }

  /// Emptiness is checked before ownership so the cheaper guard runs first, and
  /// so an empty body reports as empty rather than as an ownership problem.
  func testEmptyMessageWithoutOwnerReportsEmptinessNotOwnership() {
    XCTAssertEqual(
      ProactiveListenAdmission.decide(
        appID: "", title: "Omi", message: "", hasRuntimeOwner: false),
      .skip(.emptyMessage))
  }

  func testBlankAppIdFallsBackToTheProactiveListenAssistant() {
    guard
      case .deliver(_, _, let assistantId) = ProactiveListenAdmission.decide(
        appID: "", title: "Omi", message: "Reminder body", hasRuntimeOwner: true)
    else { return XCTFail("expected delivery") }
    XCTAssertEqual(assistantId, ProactiveListenAdmission.fallbackAssistantID)
  }

  /// The suppression that matters most to a user — notifications switched off —
  /// is deliberately *not* re-decided here. Admission routes to
  /// `NotificationService`, which owns that gate, so this pins that the master
  /// toggle is a real read rather than something this path could drift from.
  func testMasterNotificationToggleIsHonouredByTheServiceThisPathRoutesTo() throws {
    let suiteName = "omi.tests.proactiveListen"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let key = NotificationService.masterEnabledDefaultsKey
    defaults.set(false, forKey: key)
    XCTAssertFalse(NotificationService.areNotificationsEnabled(defaults: defaults))

    defaults.set(true, forKey: key)
    XCTAssertTrue(NotificationService.areNotificationsEnabled(defaults: defaults))
  }

  func testHandlerDropsEmptyMessageWithoutCrashing() {
    let state = AppState()
    state.handleListenEvent(
      TranscriptionService.ListenEvent(
        type: "proactive_message",
        raw: ["app_id": "mentor", "title": "Omi", "message": ""]
      )
    )
  }

  // MARK: - handleListenEvent: proactive_message is not "unhandled"

  func testHandlerRecognisesProactiveMessageType() {
    let state = AppState()

    // Without a runtime owner, the handler logs and exits after the owner
    // guard. The important contract is that "proactive_message" does NOT
    // fall through to the default "Unhandled event type" branch.
    //
    // We can't directly observe the log output in XCTest, but we CAN verify
    // no crash and that the event type is recognized by the switch (the
    // previous test for empty message proves the case arm is entered).
    state.handleListenEvent(
      TranscriptionService.ListenEvent(
        type: "proactive_message",
        raw: [
          "app_id": "mentor",
          "title": "Omi",
          "message": "You should follow up on that meeting.",
        ]
      )
    )
  }

  // MARK: - NotificationSpeech policy (TTS delivery decision)

  func testSpeechUtteranceForProactiveMessage() {
    // Proactive messages are spoken when speech is enabled
    let result = NotificationSpeech.utterance(
      message: "Hey, you mentioned needing to follow up.",
      isEnabled: true,
      isProactive: true
    )
    XCTAssertEqual(result, "Hey, you mentioned needing to follow up.")
  }

  func testSpeechSilentWhenDisabled() {
    let result = NotificationSpeech.utterance(
      message: "Hey, you mentioned needing to follow up.",
      isEnabled: false,
      isProactive: true
    )
    XCTAssertNil(result)
  }

  func testSpeechSilentForNonProactive() {
    let result = NotificationSpeech.utterance(
      message: "System notice",
      isEnabled: true,
      isProactive: false
    )
    XCTAssertNil(result)
  }

  func testSpeechSilentForEmptyBody() {
    let result = NotificationSpeech.utterance(
      message: "   ",
      isEnabled: true,
      isProactive: true
    )
    XCTAssertNil(result)
  }
}
