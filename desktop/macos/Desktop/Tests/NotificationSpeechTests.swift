import XCTest

@testable import Omi_Computer

final class NotificationSpeechTests: XCTestCase {
  /// The opt-in contract: a fresh install (no stored value) must never speak.
  func testDisabledByDefault() throws {
    let suiteName = "NotificationSpeechTests-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    XCTAssertFalse(NotificationSpeech.isEnabled(defaults: defaults))

    defaults.set(true, forKey: NotificationSpeech.enabledDefaultsKey)
    XCTAssertTrue(NotificationSpeech.isEnabled(defaults: defaults))
  }

  func testSilentWhenDisabledEvenWithText() {
    XCTAssertNil(
      NotificationSpeech.utterance(message: "Call dad tonight", isEnabled: false, isProactive: true))
  }

  func testSpeaksTrimmedMessageWhenEnabled() {
    XCTAssertEqual(
      NotificationSpeech.utterance(message: "  Call dad tonight \n", isEnabled: true, isProactive: true),
      "Call dad tonight")
  }

  func testSilentForWhitespaceOnlyMessage() {
    XCTAssertNil(NotificationSpeech.utterance(message: "   \n  ", isEnabled: true, isProactive: true))
  }

  /// Functional notices (onboarding test, screen-recording repair, support replies —
  /// the `respectFrequency: false` callers) must stay silent even when the user opted
  /// into spoken notifications.
  func testFunctionalNotificationStaysSilentEvenWhenEnabled() {
    XCTAssertNil(
      NotificationSpeech.utterance(
        message: "Notifications are working 🎉", isEnabled: true, isProactive: false))
  }

  /// A muted-preview fallback can present the same message on the floating bar AND the
  /// system banner; both report through the same presentation callback, so the speaker
  /// must say it exactly once.
  @MainActor
  func testEnabledDeliverySpeaksOnceAcrossDualPresentation() {
    var spoken: [String] = []
    let speaker = NotificationSpeechOnDelivery(text: "Call dad tonight") { spoken.append($0) }
    speaker.notificationWasPresented()
    speaker.notificationWasPresented()
    XCTAssertEqual(spoken, ["Call dad tonight"])
  }

  @MainActor
  func testDisabledDeliveryNeverSpeaks() {
    var spoken: [String] = []
    let speaker = NotificationSpeechOnDelivery(
      text: NotificationSpeech.utterance(message: "Call dad tonight", isEnabled: false, isProactive: true)
    ) { spoken.append($0) }
    speaker.notificationWasPresented()
    XCTAssertTrue(spoken.isEmpty)
  }
}
