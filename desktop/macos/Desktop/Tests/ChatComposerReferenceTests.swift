import XCTest

@testable import Omi_Computer

final class ChatComposerReferenceTests: XCTestCase {
  func testConversationReferenceCarriesDisplayMetadataWithoutExposingSourceID() {
    let reference = ChatComposerReference(
      kind: .conversation,
      sourceID: "capture-42",
      title: "Planning session",
      preview: "Discussed the launch plan.",
      momentTimestampMs: 74_000
    )

    XCTAssertEqual(reference.id, "conversation:capture-42")
    XCTAssertEqual(reference.displayTitle, "Planning session")
    XCTAssertEqual(reference.displaySubtitle, "Conversation · 01:14")
    XCTAssertFalse(reference.displayTitle.contains(reference.sourceID))
    XCTAssertEqual(reference.promptCitationSource.kind, .conversation)
    XCTAssertEqual(reference.promptCitationSource.sourceID, "capture-42")
    XCTAssertEqual(reference.navigationReference.kind, .conversation)
    XCTAssertEqual(reference.navigationReference.sourceID, "capture-42")
    XCTAssertEqual(reference.navigationReference.momentTimestampMs, 74_000)
    XCTAssertTrue(reference.navigationReference.canOpen)
  }

  func testStagingReplacesDuplicateAndRemovalOnlyChangesReferenceState() {
    let first = ChatComposerReference(
      kind: .conversation,
      sourceID: "capture-42",
      title: "Old title"
    )
    let refreshed = ChatComposerReference(
      kind: .conversation,
      sourceID: "capture-42",
      title: "New title"
    )
    var state = ChatComposerReferenceState()

    state.stage(first)
    state.stage(refreshed)

    XCTAssertEqual(state.references, [refreshed])
    state.remove(id: refreshed.id)
    XCTAssertTrue(state.references.isEmpty)
  }

  func testEmptySourceCannotBeStaged() {
    var state = ChatComposerReferenceState()

    state.stage(
      ChatComposerReference(
        kind: .conversation,
        sourceID: "  ",
        title: "Should not appear"
      ))

    XCTAssertTrue(state.references.isEmpty)
  }
}
