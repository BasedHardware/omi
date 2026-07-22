import XCTest

@testable import Omi_Computer

/// The ladder ordering is a product contract: an open panel always wins, voice
/// beats passive surfaces, notifications only show on an idle notch.
final class NotchPresentationLadderTests: XCTestCase {
  private let noteID = UUID()

  private func derive(
    isOpen: Bool = false,
    tab: NotchTab = .chat,
    listening: Bool = false,
    thinking: Bool = false,
    responding: Bool = false,
    hint: String = "",
    notification: UUID? = nil
  ) -> NotchPresentation {
    NotchPresentation.derive(
      isOpen: isOpen,
      tab: tab,
      isVoiceListening: listening,
      isThinking: thinking,
      isResponding: responding,
      hintText: hint,
      notificationID: notification
    )
  }

  func testIdleWhenNothingActive() {
    XCTAssertEqual(derive(), .idle)
  }

  func testOpenBeatsEverything() {
    XCTAssertEqual(
      derive(
        isOpen: true, tab: .agents, listening: true, thinking: true, responding: true, hint: "x",
        notification: noteID),
      .open(.agents))
  }

  func testListeningBeatsThinkingRespondingHintAndNotification() {
    XCTAssertEqual(
      derive(listening: true, thinking: true, responding: true, hint: "x", notification: noteID),
      .listening)
  }

  func testThinkingBeatsResponding() {
    // While awaiting the answer the reducer reports both thinking and response
    // glow; the compact thinking pill must win until the reply actually starts.
    XCTAssertEqual(derive(thinking: true, responding: true, hint: "x", notification: noteID), .thinking)
  }

  func testRespondingBeatsHintAndNotification() {
    XCTAssertEqual(derive(responding: true, hint: "x", notification: noteID), .responding)
  }

  func testHintBeatsNotification() {
    XCTAssertEqual(derive(hint: "Too short", notification: noteID), .hint("Too short"))
  }

  func testNotificationOnlyOnIdleNotch() {
    XCTAssertEqual(derive(notification: noteID), .notification(noteID))
  }

  func testExpandedSurfaceFlags() {
    XCTAssertTrue(NotchPresentation.open(.chat).isExpandedSurface)
    XCTAssertTrue(NotchPresentation.notification(noteID).isExpandedSurface)
    // The expanded voice states grow out of the notch like an opened panel.
    XCTAssertTrue(NotchPresentation.listening.isExpandedSurface)
    XCTAssertTrue(NotchPresentation.responding.isExpandedSurface)
    // Thinking is the compact pill between them.
    XCTAssertFalse(NotchPresentation.thinking.isExpandedSurface)
    XCTAssertFalse(NotchPresentation.hint("x").isExpandedSurface)
    XCTAssertFalse(NotchPresentation.idle.isExpandedSurface)
  }
}
