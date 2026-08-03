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

  func testSharedChatViewsRemainDocumentedForMainAndTaskChat() throws {
    let messagesSource = try sourceFile("MainWindow/Components/ChatMessagesView.swift")
    let inputSource = try sourceFile("MainWindow/Components/ChatInputView.swift")

    XCTAssertTrue(messagesSource.contains("Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat)."))
    XCTAssertTrue(inputSource.contains("Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat)."))
  }

  func testChatComposerUsesAThinUniformShellAndTranscriptFade() {
    XCTAssertEqual(ChatComposerLayout.shellInset, 8)
    XCTAssertEqual(ChatComposerLayout.pageMargin, 16)
    XCTAssertEqual(ChatComposerLayout.transcriptEdgeInset, ChatComposerLayout.pageMargin)
    XCTAssertGreaterThan(ChatComposerLayout.fadeHeight, ChatComposerLayout.shellInset)
    XCTAssertLessThanOrEqual(ChatComposerLayout.fadeHeight, 12)
  }

  func testOnlyConsecutiveUserRowsUseCompactSpacing() {
    let messages = [
      ChatMessage(id: "a0", text: "Answer", sender: .ai),
      ChatMessage(id: "u0", text: "First", sender: .user),
      ChatMessage(id: "u1", text: "Second", sender: .user),
      ChatMessage(id: "a1", text: "Answer", sender: .ai),
    ]

    XCTAssertEqual(ChatTranscriptLayout.topAdjustment(at: 0, in: messages), 0)
    XCTAssertEqual(ChatTranscriptLayout.topAdjustment(at: 1, in: messages), 0)
    XCTAssertEqual(
      ChatTranscriptLayout.regularRowSpacing
        + ChatTranscriptLayout.topAdjustment(at: 2, in: messages),
      ChatTranscriptLayout.consecutiveUserRowSpacing
    )
    XCTAssertEqual(ChatTranscriptLayout.topAdjustment(at: 3, in: messages), 0)
  }

  func testPromptTimelineCannotMutateTranscriptScrollerDuringLayout() throws {
    let messagesSource = try sourceFile("MainWindow/Components/ChatMessagesView.swift")
    let timelineSource = try sourceFile("MainWindow/Components/ChatPromptTimeline.swift")

    // omi-test-quality: source-inspection -- static contract: the prompt rail must stay an observational overlay; changing NSScrollView chrome from its visibility callbacks can re-enter transcript layout.
    XCTAssertFalse(messagesSource.contains("hidesNativeScrollIndicator"))
    XCTAssertFalse(messagesSource.contains("ChatTimelineScrollerSuppressionHost"))
    XCTAssertTrue(messagesSource.contains(".scrollIndicators(.hidden)"))
    XCTAssertFalse(timelineSource.contains("onVisibilityChange"))
  }

  func testPromptTimelineReceivesScrollUpdatesDuringContinuousGestures() throws {
    let scrollSource = try sourceFile("MainWindow/Components/ChatScrollBehavior.swift")

    // omi-test-quality: source-inspection -- continuous gestures must deliver the latest position on the next run-loop turn, including while AppKit is servicing event tracking.
    XCTAssertTrue(scrollSource.contains("inModes: [.common, .default, Self.eventTrackingRunLoopMode]"))
    XCTAssertTrue(scrollSource.contains("private static let eventTrackingRunLoopMode"))
    XCTAssertFalse(scrollSource.contains("asyncAfter(deadline: .now() + 0.06, execute: workItem)"))
  }

  func testScrollDetectorsRebindAfterSwiftUIReplacesTheTranscriptScrollView() throws {
    let scrollSource = try sourceFile("MainWindow/Components/ChatScrollBehavior.swift")

    // omi-test-quality: source-inspection -- AppKit representables must recover
    // when SwiftUI swaps the lazy transcript's underlying scroll hierarchy.
    XCTAssertTrue(scrollSource.contains("context.coordinator.setupScrollObserver(for: nsView)"))
    XCTAssertTrue(scrollSource.contains("observedClipView"))
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
    let dashboardSource = try sourceFile("MainWindow/Pages/DashboardPage.swift")

    // omi-test-quality: source-inspection -- static contract: the cohort shell must share the modern top-navigation and Dashboard/Home chat surfaces and must not resurrect either its retired rail or ChatPage's nested header.
    XCTAssertTrue(shellSource.contains("DesktopTopBar("))
    XCTAssertTrue(shellSource.contains("case .chat:\n      DashboardPage("))
    XCTAssertTrue(shellSource.contains("chatFirstRichBlockContext: richBlockContext"))
    XCTAssertFalse(shellSource.contains("ChatFirstSidebar("))
    XCTAssertFalse(shellSource.contains("\n      ChatPage("))
    XCTAssertTrue(dashboardSource.contains("chatFirstRichBlockContext: chatFirstRichBlockContext"))
    XCTAssertTrue(dashboardSource.contains("chatTranscriptFirstPageDidLoad()"))

    let homeSource = try sourceFile("MainWindow/DesktopHomeView.swift")
    XCTAssertTrue(homeSource.contains("if usesChatFirstShell,"))
  }

  func testMainAndNotchChatShareTheTranscriptFade() throws {
    let mainChat = try sourceFile("MainWindow/Pages/ChatPage.swift")
    let notchChat = try sourceFile("FloatingControlBar/AIResponseView.swift")

    XCTAssertTrue(mainChat.contains(".overlay(alignment: .bottom) {\n      ChatComposerFade()"))
    XCTAssertTrue(notchChat.contains(".overlay(alignment: .bottom) {\n        ChatComposerFade()"))
    XCTAssertTrue(mainChat.contains(".padding(.vertical, OmiSpacing.sm)"))
  }

  func testChatTranscriptLoaderIgnoresSessionListRefreshes() throws {
    let chatPage = try sourceFile("MainWindow/Pages/ChatPage.swift")
    let dashboardPage = try sourceFile("MainWindow/Pages/DashboardPage.swift")

    for source in [chatPage, dashboardPage] {
      XCTAssertFalse(
        source.contains("isLoadingInitial: (chatProvider.isLoading || chatProvider.isLoadingSessions)"),
        "Session-list refreshes must not hide a non-empty transcript behind the initial message-history loader."
      )
      XCTAssertFalse(
        source.contains("isLoadingInitial: chatProvider.isLoadingSessions"),
        "Session-list refreshes must not drive the transcript's initial loader."
      )
    }

    XCTAssertTrue(chatPage.contains("isLoadingInitial: chatProvider.isLoading && !chatProvider.isClearing"))
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
