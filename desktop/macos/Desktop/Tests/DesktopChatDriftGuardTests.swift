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
    XCTAssertGreaterThan(ChatComposerLayout.fadeHeight, ChatComposerLayout.shellInset)
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
