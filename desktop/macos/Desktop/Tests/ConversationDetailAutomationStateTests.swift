import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class ConversationDetailAutomationStateTests: XCTestCase {
  func testProcessingBannerReservesSpaceAboveConversationMetadata() {
    let idle = ConversationDetailProcessingLayout(isProcessing: false) {
      Color.red.frame(height: 32)
    } content: {
      Color.blue.frame(height: 20)
    }
    .frame(width: 200)

    let processing = ConversationDetailProcessingLayout(isProcessing: true) {
      Color.red.frame(height: 32)
    } content: {
      Color.blue.frame(height: 20)
    }
    .frame(width: 200)

    let idleHeight = NSHostingView(rootView: idle).fittingSize.height
    let processingHeight = NSHostingView(rootView: processing).fittingSize.height

    XCTAssertEqual(idleHeight, 20, accuracy: 0.5)
    XCTAssertEqual(processingHeight - idleHeight, 32 + OmiSpacing.xxl, accuracy: 0.5)
  }

  func testTranscriptUsesAnExclusivePaneInsteadOfCompressingTheSummaryToolbar() {
    XCTAssertEqual(ConversationDetailView.visiblePane(transcriptOpen: false), .summary)
    XCTAssertEqual(ConversationDetailView.visiblePane(transcriptOpen: true), .transcript)
  }

  func testCanonicalDetailScopesCapturePlaybackToOmiTranscriptOnly() {
    XCTAssertFalse(ConversationDetailView.showsCapturePlayback(for: .omi, in: .summary))
    XCTAssertTrue(ConversationDetailView.showsCapturePlayback(for: .omi, in: .transcript))
    XCTAssertFalse(ConversationDetailView.showsCapturePlayback(for: .desktop, in: .transcript))
    XCTAssertFalse(ConversationDetailView.showsCapturePlayback(for: nil, in: .transcript))
  }

  func testDetailRequestGateRejectsCancelledAndSupersededWork() {
    XCTAssertTrue(
      ConversationDetailRequestGate.canApply(
        requestGeneration: 2,
        currentGeneration: 2,
        isCancelled: false
      ))
    XCTAssertFalse(
      ConversationDetailRequestGate.canApply(
        requestGeneration: 1,
        currentGeneration: 2,
        isCancelled: false
      ))
    XCTAssertFalse(
      ConversationDetailRequestGate.canApply(
        requestGeneration: 2,
        currentGeneration: 2,
        isCancelled: true
      ))
  }

  private static func conversation(
    id: String = "conversation-1",
    updatedAt: Date? = Date(timeIntervalSince1970: 100),
    title: String = "Original",
    folderID: String? = nil,
    status: ConversationStatus = .completed,
    overview: String = "Summary body",
    sections: [SummarySection] = []
  ) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: Date(timeIntervalSince1970: 90),
      updatedAt: updatedAt,
      startedAt: Date(timeIntervalSince1970: 95),
      finishedAt: Date(timeIntervalSince1970: 120),
      structured: Structured(
        title: title,
        overview: overview,
        emoji: "💬",
        category: "other",
        actionItems: [],
        events: [],
        sections: sections),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: status,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: folderID,
      inputDeviceName: nil
    )
  }

  func testSameConversationVisibleRevisionRestartsCanonicalDetailLoading() {
    let original = ConversationDetailRequestToken(conversation: Self.conversation())
    let renamed = ConversationDetailRequestToken(
      conversation: Self.conversation(
        updatedAt: Date(timeIntervalSince1970: 101),
        title: "Renamed",
        folderID: "folder-1"
      )
    )

    XCTAssertNotEqual(original, renamed)
  }

  func testVolatileUpdatedAtBumpAloneDoesNotBounceTheDetailRequestToken() {
    // A background list refresh rewrites the row's Firestore revision without
    // touching anything the summary pane renders. That publish used to
    // re-assign the selected row and restart the detail task mid-read,
    // dropping the loaded summary and re-laying-out the seed underneath the
    // reader (FC-selection-overlay-layout-loop).
    let before = Self.conversation()
    let refreshed = Self.conversation(updatedAt: Date(timeIntervalSince1970: 999))

    XCTAssertEqual(
      ConversationDetailRequestToken(conversation: before),
      ConversationDetailRequestToken(conversation: refreshed))
    XCTAssertFalse(ConversationsPage.shouldReplaceSelectedConversation(before, with: refreshed))
  }

  func testSummaryContentChangeStillReplacesTheSelectedRow() {
    let contentChanges: [(String, ServerConversation)] = [
      ("overview", Self.conversation(overview: "Reprocessed summary body")),
      (
        "sections",
        Self.conversation(
          overview: "Summary body",
          sections: [SummarySection(heading: "Discussed", bodyMarkdown: "New headed block")])
      ),
    ]

    for (name, refreshed) in contentChanges {
      let before = Self.conversation()

      XCTAssertNotEqual(
        ConversationDetailRequestToken(conversation: before),
        ConversationDetailRequestToken(conversation: refreshed),
        "\(name) content change must still restart the detail load")
      XCTAssertTrue(
        ConversationsPage.shouldReplaceSelectedConversation(before, with: refreshed),
        "\(name) content change must still replace the selected row")
    }
  }

  func testStatusChangeStillReplacesTheSelectedRow() {
    let processing = Self.conversation(status: .processing)
    let completed = Self.conversation(
      updatedAt: Date(timeIntervalSince1970: 101),
      status: .completed
    )

    XCTAssertNotEqual(
      ConversationDetailRequestToken(conversation: processing),
      ConversationDetailRequestToken(conversation: completed))
    XCTAssertTrue(ConversationsPage.shouldReplaceSelectedConversation(processing, with: completed))
  }

  /// The summary pane's markdown must stay drag-selectable *through AppKit*:
  /// one `NSTextView` owning one selection, with no SwiftUI `SelectionOverlay`
  /// around the tall block (FC-selection-overlay-layout-loop). The boundary
  /// script forbids the SwiftUI ancestor statically; this asserts the
  /// behavioral half — the sanctioned host really is mounted and selectable.
  func testSummaryMarkdownHostsSelectableAppKitProse() throws {
    let prose = "A **long** summary with `code` and an [example](https://example.com) link."
    let hostingView = NSHostingView(
      rootView: OmiMarkdown(text: prose, sender: .ai, appKitProseSelection: true)
        .frame(width: 360, alignment: .leading))
    hostingView.frame = NSRect(x: 0, y: 0, width: 360, height: 200)
    let window = NSWindow(
      contentRect: hostingView.frame,
      styleMask: [.titled], backing: .buffered, defer: false)
    window.contentView = hostingView
    NonintrusiveTestWindow.orderIn(window)
    RunLoop.current.run(until: Date().addingTimeInterval(0.2))
    hostingView.layoutSubtreeIfNeeded()
    RunLoop.current.run(until: Date().addingTimeInterval(0.2))
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }

    let textViews = Self.descend(NSTextView.self, from: hostingView)
    XCTAssertFalse(textViews.isEmpty, "selectable summary prose must mount an NSTextView")

    let rendered = textViews.map(\.string).joined(separator: "\n")
    XCTAssertTrue(rendered.contains("long summary"), "markdown must render, not show syntax: \(rendered)")
    XCTAssertFalse(rendered.contains("**"), "bold markers must not render literally: \(rendered)")

    for textView in textViews {
      XCTAssertTrue(textView.isSelectable, "drag-select is the reader's copy path")
      XCTAssertFalse(textView.isEditable)
    }
  }

  private static func descend<T: NSView>(_ type: T.Type, from view: NSView) -> [T] {
    var matches: [T] = []
    if let match = view as? T { matches.append(match) }
    for subview in view.subviews { matches += descend(type, from: subview) }
    return matches
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

    state.requestOpen(
      conversationId: "conversation-1",
      showTranscript: true,
      transcriptSegmentIds: ["segment-2"]
    )
    _ = state.syncPresentedDetail(conversationId: "conversation-1", transcriptDrawerOpen: true)
    let drawerOpen = state.syncPresentedDetail(conversationId: "conversation-2", transcriptDrawerOpen: false)

    XCTAssertEqual(state.openConversationId, "conversation-2")
    XCTAssertFalse(drawerOpen)
    XCTAssertFalse(state.transcriptDrawerOpen)
    XCTAssertTrue(state.focusedTranscriptSegmentIds.isEmpty)
  }
}
