import XCTest

@testable import Omi_Computer

@MainActor
final class MeetingNoteTakingNoticeTests: XCTestCase {
  /// Counts presentations for the duration of one test. XCTest's lifecycle
  /// hooks are nonisolated, so the main-actor presenter is saved and restored
  /// inside the test body instead.
  @MainActor
  private final class PresentationCounter {
    private(set) var count = 0
    // Captured in `init`, not as a default value: a stored property's default
    // expression is nonisolated even when the type is @MainActor, so reading
    // the main-actor presenter there fails under strict concurrency.
    private let original: () -> Void

    init() {
      original = MeetingNoteTakingNotice.present
      MeetingNoteTakingNotice.present = { [weak self] in self?.count += 1 }
    }

    func restore() {
      MeetingNoteTakingNotice.present = original
    }

    private func increment() { count += 1 }
  }

  /// The card states what already happened rather than asking permission, so
  /// its copy must stay a statement — a question here would re-introduce the
  /// prompt the notice deliberately replaces.
  func testNoticeCopyIsAStatementNotAPrompt() {
    XCTAssertEqual(MeetingNoteTakingNotice.title, "Meeting detected")
    XCTAssertEqual(MeetingNoteTakingNotice.message, "Omi is taking notes")
    XCTAssertFalse(MeetingNoteTakingNotice.message.contains("?"))
  }

  // MARK: - When the notice is owed

  func testAnnouncedOnlyWhenTheMeetingRoleActuallyCommitted() {
    XCTAssertTrue(
      MeetingConversationBoundaryPolicy.shouldAnnounceNoteTaking(
        committedRole: .meeting, rotationSucceeded: true))
  }

  func testNotAnnouncedWhenTheRotationFailed() {
    // Capture stays on the previous role, so note-taking did not start.
    XCTAssertFalse(
      MeetingConversationBoundaryPolicy.shouldAnnounceNoteTaking(
        committedRole: .meeting, rotationSucceeded: false))
    XCTAssertFalse(
      MeetingConversationBoundaryPolicy.shouldAnnounceNoteTaking(
        committedRole: .ambient, rotationSucceeded: false))
  }

  func testNotAnnouncedWhenTheMeetingEnded() {
    XCTAssertFalse(
      MeetingConversationBoundaryPolicy.shouldAnnounceNoteTaking(
        committedRole: .ambient, rotationSucceeded: true))
  }

  // MARK: - Driven through the real boundary

  /// Drives `AppState.handleMeetingObservation` — the production entry point the
  /// meeting detector calls — with no owned session. The boundary must refuse to
  /// rotate, and with no committed meeting role the notice must not fire: this is
  /// the path that would otherwise announce note-taking that never started.
  func testBoundaryWithoutAnOwnedSessionDoesNotAnnounce() async {
    let counter = PresentationCounter()
    defer { counter.restore() }

    let state = AppState()
    state.isTranscribing = true
    state.currentSessionId = nil
    state.currentConversationRole = .ambient

    await state.handleMeetingObservation(active: true)

    XCTAssertEqual(counter.count, 0)
    XCTAssertEqual(state.currentConversationRole, .ambient)
  }

  /// A detector edge while transcription is off must not announce either — the
  /// notice would be claiming notes for a session that is not recording.
  func testBoundaryWhileNotTranscribingDoesNotAnnounce() async {
    let counter = PresentationCounter()
    defer { counter.restore() }

    let state = AppState()
    state.isTranscribing = false
    state.currentConversationRole = .ambient

    await state.handleMeetingObservation(active: true)

    XCTAssertEqual(counter.count, 0)
  }
}
