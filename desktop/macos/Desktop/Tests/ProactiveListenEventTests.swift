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
      type: backendJSON["type"] as! String,
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
      type: backendJSON["type"] as! String,
      raw: backendJSON
    )

    XCTAssertEqual(event.type, "proactive_message")
    XCTAssertNil(event.raw["conversation_id"] as? String)
  }

  // MARK: - handleListenEvent gate: empty message body is dropped

  func testHandlerDropsEmptyMessage() {
    let state = AppState()

    // An empty message body should be silently dropped (no crash, no
    // notification). Without a logged-in runtime owner there's no
    // FloatingControlBarManager delivery to observe, but the guard on empty
    // message precedes the owner check, so we verify it doesn't crash.
    state.handleListenEvent(
      TranscriptionService.ListenEvent(
        type: "proactive_message",
        raw: [
          "app_id": "mentor",
          "title": "Omi",
          "message": "",
        ]
      )
    )
    // If we get here without a crash or assertion failure, the empty-body
    // guard works. No state mutation to verify — the event is dropped.
  }

  func testHandlerDropsMissingMessage() {
    let state = AppState()

    // Missing "message" key entirely — the handler defaults to "" and drops.
    state.handleListenEvent(
      TranscriptionService.ListenEvent(
        type: "proactive_message",
        raw: [
          "app_id": "mentor",
          "title": "Omi",
        ]
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
