import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationDetailAutomationStateTests: XCTestCase {
  func testTranscriptUsesAnExclusivePaneInsteadOfCompressingTheSummaryToolbar() {
    XCTAssertEqual(ConversationDetailView.visiblePane(transcriptOpen: false), .summary)
    XCTAssertEqual(ConversationDetailView.visiblePane(transcriptOpen: true), .transcript)
  }

  func testPendingOpenSurvivesUntilTheConversationsPageConsumesIt() {
    let state = ConversationDetailAutomationState()

    state.requestOpen(conversationId: "conversation-1", showTranscript: true)

    XCTAssertEqual(
      state.takePendingOpenRequest(),
      .init(conversationId: "conversation-1", showTranscript: true)
    )
    XCTAssertNil(state.takePendingOpenRequest())
  }

  func testAppearingDetailConsumesTranscriptIntentWithoutDelay() {
    let state = ConversationDetailAutomationState()

    state.requestOpen(conversationId: "conversation-1", showTranscript: true)
    _ = state.takePendingOpenRequest()

    XCTAssertTrue(state.syncPresentedDetail(conversationId: "conversation-1", transcriptDrawerOpen: false))
    XCTAssertEqual(state.openConversationId, "conversation-1")
    XCTAssertTrue(state.transcriptDrawerOpen)
  }

  func testTranscriptEvidenceSurvivesNavigationAndFocusesPresentedDetail() {
    let state = ConversationDetailAutomationState()
    state.requestOpen(
      conversationId: "conversation-1",
      showTranscript: true,
      transcriptSegmentIds: ["segment-2"]
    )

    _ = state.takePendingOpenRequest()
    XCTAssertTrue(state.syncPresentedDetail(conversationId: "conversation-1", transcriptDrawerOpen: false))
    XCTAssertEqual(state.focusedTranscriptSegmentIds, ["segment-2"])
  }

  func testLaterRequestWithoutTranscriptReplacesEarlierDrawerIntent() {
    let state = ConversationDetailAutomationState()

    state.requestOpen(conversationId: "conversation-1", showTranscript: true)
    state.requestOpen(conversationId: "conversation-2", showTranscript: false)
    _ = state.takePendingOpenRequest()

    XCTAssertFalse(state.syncPresentedDetail(conversationId: "conversation-2", transcriptDrawerOpen: false))
    XCTAssertFalse(state.transcriptDrawerOpen)
  }

  func testNormalDetailOpenDoesNotShowTranscriptDrawer() {
    let state = ConversationDetailAutomationState()

    XCTAssertFalse(state.syncPresentedDetail(conversationId: "conversation-1", transcriptDrawerOpen: false))
    XCTAssertFalse(state.transcriptDrawerOpen)
  }

  func testTranscriptRequestForAlreadyOpenConversationPublishesDrawerState() {
    let state = ConversationDetailAutomationState()
    _ = state.syncPresentedDetail(conversationId: "conversation-1", transcriptDrawerOpen: false)

    state.requestOpen(conversationId: "conversation-1", showTranscript: true)

    XCTAssertTrue(state.transcriptDrawerOpen)
  }

  func testSyncPresentedDetailReplacesAutomationOpenStateWhenSwiftUIReusesTheDetailView() {
    let state = ConversationDetailAutomationState()

    _ = state.syncPresentedDetail(conversationId: "conversation-1", transcriptDrawerOpen: true)
    let drawerOpen = state.syncPresentedDetail(conversationId: "conversation-2", transcriptDrawerOpen: false)

    XCTAssertEqual(state.openConversationId, "conversation-2")
    XCTAssertFalse(drawerOpen)
    XCTAssertFalse(state.transcriptDrawerOpen)
  }
}
