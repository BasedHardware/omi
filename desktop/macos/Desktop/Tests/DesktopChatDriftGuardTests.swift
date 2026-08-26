import XCTest

@testable import Omi_Computer

final class DesktopChatDriftGuardTests: XCTestCase {
  private let allowedChatProviderMirrorMarkers: Set<String> = []

  func testTaskChatPanelUsesSharedChatViews() throws {
    let source = try sourceFile("MainWindow/Components/TaskChatPanel.swift")

    XCTAssertTrue(source.contains("ChatMessagesView("))
    XCTAssertTrue(source.contains("ChatInputView("))
    XCTAssertTrue(source.contains("localSendToken: taskState.localSendToken"))
    XCTAssertTrue(source.contains("onStop: {"))
    XCTAssertFalse(source.contains("OmiTextEditor("))
    XCTAssertFalse(source.contains("TypingIndicator()"))
    XCTAssertFalse(source.contains("ToolCallsGroup("))
    XCTAssertFalse(source.contains("ThinkingBlock("))
  }

  func testTaskChatPanelDisablesPushToTalkUntilTaskThreadRoutingExists() throws {
    let source = try sourceFile("MainWindow/Components/TaskChatPanel.swift")

    // omi-test-quality: source-inspection -- static contract: this caller must
    // opt out of ChatInputView's global PTT route until task-thread voice
    // routing is implemented.
    let inputStart = try XCTUnwrap(source.range(of: "            ChatInputView("))
    let inputEnd = try XCTUnwrap(
      source.range(of: "\n            )", range: inputStart.upperBound..<source.endIndex)
    )
    let inputCall = source[inputStart.lowerBound..<inputEnd.lowerBound]
    XCTAssertTrue(
      inputCall.contains("showsPushToTalk: false"),
      "TaskChatPanel must explicitly disable the shared composer's PTT control"
    )
  }

  func testSharedChatViewsRemainDocumentedForMainAndTaskChat() throws {
    let messagesSource = try sourceFile("MainWindow/Components/ChatMessagesView.swift")
    let inputSource = try sourceFile("MainWindow/Components/ChatInputView.swift")

    // Deliberately not pinned to whichever name the main surface currently has:
    // the contract is that both views stay documented as shared with the task
    // sidebar, not what the other caller happens to be called this month.
    XCTAssertTrue(messagesSource.contains("and TaskChatPanel (task sidebar chat)."))
    XCTAssertTrue(inputSource.contains("and TaskChatPanel (task sidebar chat)."))
  }

  func testChatComposerUsesAThinUniformShellAndTranscriptFade() {
    XCTAssertEqual(ChatComposerLayout.shellInset, 8)
    XCTAssertEqual(ChatComposerLayout.pageMargin, 16)
    XCTAssertEqual(ChatComposerLayout.transcriptEdgeInset, ChatComposerLayout.pageMargin)
    XCTAssertGreaterThan(ChatComposerLayout.fadeHeight, ChatComposerLayout.shellInset)
    XCTAssertLessThanOrEqual(ChatComposerLayout.fadeHeight, 12)
  }

  /// **A reply sits closer to its question than to the next one.** That
  /// difference is the only thing in the layout that says which answer belongs to
  /// which question; with one uniform gap a column of short messages reads as
  /// scattered text, which is exactly what it did.
  func testAReplySitsCloserToItsQuestionThanTheNextExchangeDoes() {
    let messages = [
      ChatMessage(id: "a0", text: "Answer", sender: .ai),
      ChatMessage(id: "u0", text: "First", sender: .user),
      ChatMessage(id: "u1", text: "Second", sender: .user),
      ChatMessage(id: "a1", text: "Answer", sender: .ai),
      ChatMessage(id: "u2", text: "Third", sender: .user),
    ]

    func gap(_ index: Int) -> CGFloat {
      ChatTranscriptLayout.regularRowSpacing
        + ChatTranscriptLayout.topAdjustment(at: index, in: messages)
    }

    XCTAssertEqual(ChatTranscriptLayout.topAdjustment(at: 0, in: messages), 0)
    // assistant → user starts a new exchange and takes the full gap.
    XCTAssertEqual(gap(1), ChatTranscriptLayout.regularRowSpacing)
    XCTAssertEqual(gap(2), ChatTranscriptLayout.consecutiveUserRowSpacing)
    // user → assistant is one exchange, so it is the tight gap.
    XCTAssertEqual(gap(3), ChatTranscriptLayout.replySpacing)
    XCTAssertEqual(gap(4), ChatTranscriptLayout.regularRowSpacing)

    XCTAssertLessThan(
      ChatTranscriptLayout.replySpacing, ChatTranscriptLayout.regularRowSpacing,
      "a reply must bind to its question more tightly than to the next exchange")
  }

  /// The gap after an assistant row is also the room its hover-revealed metadata
  /// band draws into — that band is zero-height at rest, so the space has to come
  /// from somewhere, and it comes from here.
  func testTheGapAfterAnAssistantRowStaysWideEnoughForItsHoverBand() {
    let messages = [
      ChatMessage(id: "a0", text: "Answer", sender: .ai),
      ChatMessage(id: "a1", text: "Also this", sender: .ai),
    ]
    XCTAssertEqual(
      ChatTranscriptLayout.spacing(from: messages[0], to: messages[1]),
      ChatTranscriptLayout.regularRowSpacing)
  }

  func testTranscriptScrollerPolicyIsStaticAndSingle() throws {
    let messagesSource = try sourceFile("MainWindow/Components/ChatMessagesView.swift")

    // omi-test-quality: source-inspection -- static contract: the transcript owns exactly one
    // vertical scroll affordance, and its chrome policy never changes at runtime. Mutating
    // NSScrollView's scroller visibility during layout can re-enter the transcript's own pass.
    XCTAssertFalse(messagesSource.contains("hidesNativeScrollIndicator"))
    XCTAssertFalse(messagesSource.contains("ChatTimelineScrollerSuppressionHost"))
    // `.never`, not `.hidden`. Both are static, so the no-runtime-mutation reason
    // this test exists for is unchanged — but per Apple's `ScrollIndicatorVisibility`
    // documentation `.hidden` only requests hiding, while `.never` overrides
    // scrollable components that would otherwise show the scroller. AppKit took the
    // former as advisory and drew the overlay scroller over the panel's rounded edge.
    XCTAssertTrue(messagesSource.contains(".scrollIndicators(.never)"))
    XCTAssertFalse(messagesSource.contains(".scrollIndicators(.hidden)"))
    // The prompt rail is the one visual scroll affordance: hairline marks overlaid
    // on the trailing edge. It must not reserve a column that insets the messages.
    XCTAssertFalse(messagesSource.contains("contentColumnWidth"))
    XCTAssertTrue(messagesSource.contains("ChatPromptTimelineOverlay"))
  }

  func testTheScrollDetectorRebindsAfterSwiftUIReplacesTheTranscriptScrollView() throws {
    let scrollSource = try sourceFile("MainWindow/Components/ChatScrollBehavior.swift")

    // omi-test-quality: source-inspection -- AppKit representables must recover
    // when SwiftUI swaps the lazy transcript's underlying scroll hierarchy.
    XCTAssertTrue(scrollSource.contains("context.coordinator.install(for: nsView)"))
    XCTAssertTrue(scrollSource.contains("installedScrollView"))
  }

  func testChatStartsAtBottomOnLaunchButPreservesExplicitReaderScroll() throws {
    let messagesSource = try sourceFile("MainWindow/Components/ChatMessagesView.swift")

    // omi-test-quality: source-inspection -- launch placement is owned by the
    // cancelable state machine. An unconditional SwiftUI default anchor is a
    // second authority that can pull an explicitly free-scrolled reader back.
    XCTAssertFalse(messagesSource.contains(".defaultScrollAnchor(.bottom)"))
    XCTAssertTrue(messagesSource.contains("ChatInitialRestoreState.afterDisappear"))
    XCTAssertTrue(messagesSource.contains("cancelPendingScrollsForUserInteraction()"))
    XCTAssertTrue(messagesSource.contains("initialRestoreState = .completed"))
  }

  func testPermissionRefreshPreservesStateWhenSystemEventsIsStopped() throws {
    let source = try sourceFile("AppState/AppState+Permissions.swift")
    let start = try XCTUnwrap(source.range(of: "if status == -600"))
    let snippet = String(source[start.lowerBound...]).prefix(320)

    XCTAssertFalse(snippet.contains("hasAutomationPermission = false"))
    XCTAssertFalse(snippet.contains("automationPermissionError = 0"))
  }

  func testGoogleConnectorProbesUseExplicitUserInitiatedReads() throws {
    let source = try sourceFile("DesktopAutomationBridge.swift")
    for action in ["calendar_read_probe", "gmail_read_probe"] {
      guard let start = source.range(of: "name: \"\(action)\"") else {
        return XCTFail("missing \(action)")
      }
      let tail = source[start.lowerBound...]
      let body = tail.range(of: "\n    register(").map { String(tail[..<$0.lowerBound]) } ?? String(tail)
      XCTAssertTrue(body.contains("userInitiated: true"), "\(action) must declare explicit user intent")
    }
  }

  func testScrollHandoffCannotBeRearmedByStaleBottomChecks() throws {
    let scrollSource = try sourceFile("MainWindow/Components/ChatScrollBehavior.swift")
    let messagesSource = try sourceFile("MainWindow/Components/ChatMessagesView.swift")

    // omi-test-quality: source-inspection -- passive position updates and
    // settled checks must both use the active-gesture fence before restoring
    // live following. Wheel momentum is owned by AppKit's live-scroll
    // lifecycle, never by a guessed wall-clock delay.
    XCTAssertTrue(scrollSource.contains("private var settleWorkItem: DispatchWorkItem?"))
    XCTAssertFalse(scrollSource.contains("for delay in [0.12, 0.36]"))
    XCTAssertTrue(scrollSource.contains("NSScrollView.willStartLiveScrollNotification"))
    XCTAssertTrue(scrollSource.contains("NSScrollView.didEndLiveScrollNotification"))
    XCTAssertTrue(scrollSource.contains("scheduleDiscreteInputSettledBottomCheck"))
    XCTAssertTrue(scrollSource.contains("ChatScrollLiveEdge.canResumeFollowing"))
    XCTAssertTrue(messagesSource.contains("ChatScrollLiveEdge.canResumeFollowing"))
  }

  func testChatFirstShellUsesModernTopNavigation() throws {
    let shellSource = try sourceFile("MainWindow/ChatFirst/ChatFirstShell.swift")
    let queryHomeSource = try sourceFile("MainWindow/QueryShell/QueryShellHome.swift")
    let answerThreadSource = try sourceFile("MainWindow/QueryShell/QueryAnswerThread.swift")
    let dashboardSource = try sourceFile("MainWindow/Pages/DashboardPage.swift")

    // omi-test-quality: source-inspection -- static contract: the Chat-first shell must share the modern
    // top-navigation and the single QueryShellHome chat surface, while rich-block capability and
    // visible-transcript lifecycle remain threaded through the shared answer view.
    XCTAssertTrue(shellSource.contains("DesktopTopBar("))
    XCTAssertTrue(shellSource.contains("case .chat:\n      QueryShellHome("))
    XCTAssertFalse(shellSource.contains("case .chat:\n      DashboardPage("))
    XCTAssertTrue(shellSource.contains("forceModernPresentation: true"))
    XCTAssertTrue(shellSource.contains("chatFirstRichBlockContext: richBlockContext"))
    XCTAssertTrue(queryHomeSource.contains("forceModernPresentation"))
    XCTAssertTrue(queryHomeSource.contains("chatFirstRichBlockContext: chatFirstRichBlockContext"))
    XCTAssertTrue(answerThreadSource.contains("chatFirstRichBlockContext: chatFirstRichBlockContext"))
    XCTAssertTrue(answerThreadSource.contains("chatTranscriptFirstPageDidLoad()"))
    XCTAssertTrue(answerThreadSource.contains("chatTranscriptDidDisappear()"))
    XCTAssertFalse(shellSource.contains("ChatFirstSidebar("))
    XCTAssertFalse(shellSource.contains("\n      ChatPage("))
    XCTAssertTrue(dashboardSource.contains("chatFirstRichBlockContext: chatFirstRichBlockContext"))
    XCTAssertTrue(dashboardSource.contains("chatTranscriptFirstPageDidLoad()"))

    let homeSource = try sourceFile("MainWindow/DesktopHomeView.swift")
    XCTAssertTrue(homeSource.contains("if usesChatFirstShell,"))
  }

  /// The fade is the notch's alone now that the standalone chat page is gone.
  /// Home deliberately does not mask its transcript viewport — the ask bar
  /// already draws its own boundary, and a mask there clips the first lines of
  /// an incoming reply — so this pins the notch and pins Home's abstention.
  func testTheTranscriptFadeIsTheNotchsAloneAndHomeAbstains() throws {
    let notchChat = try sourceFile("FloatingControlBar/AIResponseView.swift")
    let home = try sourceFile("MainWindow/Pages/DashboardPage.swift")

    XCTAssertTrue(notchChat.contains(".overlay(alignment: .bottom) {\n        ChatComposerFade()"))
    XCTAssertFalse(
      home.contains("ChatComposerFade()"),
      "Home's transcript must stay unmasked; a fade there cuts off incoming replies.")
  }

  func testChatTranscriptLoaderIgnoresSessionListRefreshes() throws {
    let dashboardPage = try sourceFile("MainWindow/Pages/DashboardPage.swift")

    for source in [dashboardPage] {
      XCTAssertFalse(
        source.contains("isLoadingInitial: (chatProvider.isLoading || chatProvider.isLoadingSessions)"),
        "Session-list refreshes must not hide a non-empty transcript behind the initial message-history loader."
      )
      XCTAssertFalse(
        source.contains("isLoadingInitial: chatProvider.isLoadingSessions"),
        "Session-list refreshes must not drive the transcript's initial loader."
      )
    }

    XCTAssertEqual(
      dashboardPage.components(separatedBy: "isLoadingInitial: chatProvider.isLoading && !chatProvider.isClearing")
        .count - 1,
      2
    )
  }

  func testNoNewMirroredFromChatProviderTaskChatHelperBlocks() throws {
    let markers = try swiftSourceLines(containingAnyOf: [
      "mirrored from ChatProvider",
      "Mirrors ChatProvider",
    ])
    .filter { !$0.path.hasSuffix("DesktopChatDriftGuardTests.swift") }
    .map {
      "\($0.path):\($0.line.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "\u{2014}", with: "-"))"
    }

    let unexpectedMarkers = Set(markers).subtracting(allowedChatProviderMirrorMarkers)

    XCTAssertTrue(
      unexpectedMarkers.isEmpty,
      """
      Task-chat should share ChatProvider helpers instead of adding new copied "mirrored from ChatProvider" blocks.
      If the legacy TaskChatState markers are removed by a refactor, delete them from allowedChatProviderMirrorMarkers.
      Unexpected markers:
      \(unexpectedMarkers.sorted().joined(separator: "\n"))
      """
    )
  }

  func testTaskChatStreamingStatusUsesSharedStreamingBuffer() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")
    let bufferSource = try sourceFile("Chat/ChatStreamingBuffer.swift")

    XCTAssertTrue(source.contains("ChatStreamingBuffer("))
    XCTAssertTrue(source.contains("streamingBuffer.appendText("))
    XCTAssertTrue(source.contains("streamingBuffer.applyToolActivity("))
    XCTAssertTrue(source.contains("streamingBuffer.applyToolResult("))
    XCTAssertTrue(source.contains("streamingBuffer.completeRemainingToolCalls("))
    XCTAssertTrue(bufferSource.contains("ToolCallBlockUpdater.applyToolActivity("))
    XCTAssertTrue(bufferSource.contains("ToolCallBlockUpdater.applyToolOutput("))
    XCTAssertTrue(bufferSource.contains("ToolCallBlockUpdater.completeRemainingToolCalls("))
    XCTAssertFalse(source.contains("ChatProvider.mapBridgeToolStatus("))
    XCTAssertFalse(source.contains("ChatProvider.remainingToolStatusAfterPartialResponseError("))
  }

  private struct SourceLine {
    let path: String
    let line: String
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    try String(contentsOf: sourcesRoot().appendingPathComponent(relativePath), encoding: .utf8)
  }

  private func swiftSourceLines(containingAnyOf needles: [String]) throws -> [SourceLine] {
    let root = sourcesRoot()
    let paths = try FileManager.default.subpathsOfDirectory(atPath: root.path)
      .filter { $0.hasSuffix(".swift") }
      .sorted()

    var matches: [SourceLine] = []
    for path in paths {
      let text = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
      for line in text.components(separatedBy: .newlines)
      where needles.contains(where: { line.contains($0) }) {
        matches.append(SourceLine(path: path, line: line))
      }
    }
    return matches
  }

  private func sourcesRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
  }
}
