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
    hint: String = "",
    notification: UUID? = nil
  ) -> NotchPresentation {
    NotchPresentation.derive(
      isOpen: isOpen,
      tab: tab,
      isVoiceListening: listening,
      isThinking: thinking,
      hintText: hint,
      notificationID: notification
    )
  }

  func testIdleWhenNothingActive() {
    XCTAssertEqual(derive(), .idle)
  }

  func testOpenBeatsEverything() {
    XCTAssertEqual(
      derive(isOpen: true, tab: .agents, listening: true, thinking: true, hint: "x", notification: noteID),
      .open(.agents))
  }

  func testListeningBeatsThinkingHintAndNotification() {
    XCTAssertEqual(
      derive(listening: true, thinking: true, hint: "x", notification: noteID), .listening)
  }

  func testThinkingBeatsHintAndNotification() {
    XCTAssertEqual(derive(thinking: true, hint: "x", notification: noteID), .thinking)
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
    XCTAssertFalse(NotchPresentation.listening.isExpandedSurface)
    XCTAssertFalse(NotchPresentation.thinking.isExpandedSurface)
    XCTAssertFalse(NotchPresentation.hint("x").isExpandedSurface)
    XCTAssertFalse(NotchPresentation.idle.isExpandedSurface)
  }
}
