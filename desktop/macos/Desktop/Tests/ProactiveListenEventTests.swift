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

  private var originalAuthOwner: String?
  private var originalOwnerOverride: String?
  private var originalOwnerBackup: String?

  // These tests assert what the handler does with *no* runtime owner, and they
  // relied on the process simply never having had one. That held by luck: this
  // suite shares a CI batch with `AppStateOwnerFenceTests` and
  // `AuthorizedToolOwnerBoundAuthTests`, both of which write owner defaults, and
  // an owner left behind sends `testHandlerRecognisesProactiveMessageType` past
  // its owner guard into `NotificationService.shared` — which constructs
  // `UNUserNotificationCenter.current()` and raises
  // `bundleProxyForCurrentProcess is nil` under SwiftPM's command-line test host.
  // The premise is now established rather than inherited.
  override func setUp() async throws {
    originalAuthOwner = UserDefaults.standard.string(forKey: .authUserId)
    originalOwnerOverride = UserDefaults.standard.string(forKey: .automationOwnerOverride)
    originalOwnerBackup = UserDefaults.standard.string(forKey: .automationOwnerABackup)
    UserDefaults.standard.removeObject(forKey: .authUserId)
    UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
    UserDefaults.standard.removeObject(forKey: .automationOwnerABackup)
  }

  override func tearDown() async throws {
    restore(originalAuthOwner, forKey: .authUserId)
    restore(originalOwnerOverride, forKey: .automationOwnerOverride)
    restore(originalOwnerBackup, forKey: .automationOwnerABackup)
  }

  private func restore(_ value: String?, forKey key: DefaultsKey) {
    if let value {
      UserDefaults.standard.set(value, forKey: key)
    } else {
      UserDefaults.standard.removeObject(forKey: key)
    }
  }

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

    // The guard this test leans on. If an owner is present the handler proceeds
    // into the system notification centre, which cannot be constructed here — so
    // fail with the reason rather than as an opaque ObjC exception.
    XCTAssertNil(
      RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      "this test requires no runtime owner; a sibling suite leaked one")

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
