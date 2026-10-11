import XCTest

@testable import Omi_Computer

/// The summary's action-item rows show their controls only where the reader is looking, except for
/// task states the reader has to see.
final class ActionItemRowActionVisibilityTests: XCTestCase {
  func testIdleRowHidesBothControlsAtRest() {
    XCTAssertFalse(
      ActionItemRowActionVisibility.showsTaskAction(state: .idle, isHovered: false, hasFocus: false))
    XCTAssertFalse(ActionItemRowActionVisibility.showsTranscriptAction(isHovered: false, hasFocus: false))
  }

  func testHoverOrKeyboardFocusRevealsBothControls() {
    for (hovered, focused) in [(true, false), (false, true), (true, true)] {
      XCTAssertTrue(
        ActionItemRowActionVisibility.showsTaskAction(state: .idle, isHovered: hovered, hasFocus: focused))
      XCTAssertTrue(ActionItemRowActionVisibility.showsTranscriptAction(isHovered: hovered, hasFocus: focused))
    }
  }

  func testEveryNonIdleTaskStateStaysVisibleAtRest() {
    for state in [ActionItemTaskState.adding, .added, .failed, .linked] {
      XCTAssertTrue(
        ActionItemRowActionVisibility.showsTaskAction(state: state, isHovered: false, hasFocus: false),
        "\(state) is state the reader must see without hovering")
    }
  }

  func testOnlyStatesWithSomethingToDoAreActionable() {
    XCTAssertTrue(ActionItemTaskState.idle.isActionable)
    XCTAssertTrue(ActionItemTaskState.failed.isActionable)
    XCTAssertTrue(ActionItemTaskState.linked.isActionable)
    XCTAssertFalse(ActionItemTaskState.adding.isActionable)
    XCTAssertFalse(ActionItemTaskState.added.isActionable)
    XCTAssertEqual(ActionItemTaskState.failed.actionTitle, "Try Again")
    XCTAssertEqual(ActionItemTaskState.idle.actionTitle, "Add to Tasks")
  }
}

/// Which segments the speaker sheet changes, and when it offers to unassign.
@MainActor
final class NameSpeakerSheetGroupingTests: XCTestCase {
  private func segment(_ id: String, speaker: String, isUser: Bool = false, personId: String? = nil)
    -> TranscriptSegment
  {
    TranscriptSegment(
      id: id, backendId: nil, text: id, speaker: speaker, isUser: isUser,
      personId: personId, start: 0, end: 1, translations: [])
  }

  func testAnonymousOrNamedSpeakerGroupsItsNonUserSegmentsOnly() {
    let segments = [
      segment("a", speaker: "SPEAKER_01"),
      segment("b", speaker: "SPEAKER_01", personId: "dana"),
      segment("c", speaker: "SPEAKER_01", isUser: true),
      segment("d", speaker: "SPEAKER_02"),
    ]
    XCTAssertEqual(NameSpeakerSheet.sameSpeakerIndices(of: segments[0], in: segments), [0, 1])
  }

  /// Unassigning a wrong "You" must reach the tapped segment and its "You" siblings. The old filter
  /// dropped every user segment, so the tapped one was never part of its own save.
  func testYouSegmentGroupsWithItsOtherYouSegments() {
    let segments = [
      segment("a", speaker: "SPEAKER_01", isUser: true),
      segment("b", speaker: "SPEAKER_01"),
      segment("c", speaker: "SPEAKER_01", isUser: true),
    ]
    XCTAssertEqual(NameSpeakerSheet.sameSpeakerIndices(of: segments[2], in: segments), [0, 2])
  }

  func testUnassignIsOfferedOnlyWhenThereIsAnIdentityToRemove() {
    XCTAssertFalse(NameSpeakerSheet.canUnassign(segment("a", speaker: "SPEAKER_01")))
    XCTAssertTrue(NameSpeakerSheet.canUnassign(segment("a", speaker: "SPEAKER_01", personId: "dana")))
    XCTAssertTrue(NameSpeakerSheet.canUnassign(segment("a", speaker: "SPEAKER_01", isUser: true)))
  }
}
