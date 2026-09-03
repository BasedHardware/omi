import XCTest

@testable import Omi_Computer

/// The wire delivers an answer in bursts; the transcript should show it as a
/// flow. These pin the pacing that turns one into the other.
final class ChatStreamingRevealTests: XCTestCase {
  func testASmallBacklogDrainsOverAFewFlushes() {
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 100), 20)
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 10), ChatStreamingReveal.minimumPerFlush)
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 3), 3, "never more than is pending")
    XCTAssertEqual(ChatStreamingReveal.characters(pending: 0), 0)
  }

  func testALargeBacklogCatchesUpToTheLagCap() {
    let revealed = ChatStreamingReveal.characters(pending: 2000)
    XCTAssertEqual(2000 - revealed, ChatStreamingReveal.maximumLag, "a paragraph from a tool lands almost at once")
  }

  private func makeMessages() -> [ChatMessage] {
    [ChatMessage(id: "m", text: "", sender: .ai, isStreaming: true)]
  }

  func testAPacedFlushRevealsASliceAndKeepsTheRestQueued() {
    let buffer = ChatStreamingBuffer(flushInterval: 10)
    var messages = makeMessages()
    buffer.appendText(messageId: "m", text: String(repeating: "a", count: 100), scheduleFlush: {})

    XCTAssertTrue(buffer.flushPaced(messages: &messages), "most of the burst is still waiting")
    XCTAssertEqual(messages[0].text.count, 20)
    XCTAssertEqual(buffer.pendingTextCount, 80)

    XCTAssertTrue(buffer.flushPaced(messages: &messages))
    XCTAssertEqual(messages[0].text.count, 36, "each flush takes a fifth of what remains")

    buffer.flush(messages: &messages)
    XCTAssertEqual(messages[0].text.count, 100)
    XCTAssertFalse(buffer.flushPaced(messages: &messages), "nothing left once drained")
  }

  func testThinkingStaysBehindTheTextItFollows() {
    let buffer = ChatStreamingBuffer(flushInterval: 10)
    var messages = makeMessages()
    buffer.appendText(messageId: "m", text: String(repeating: "a", count: 100), scheduleFlush: {})
    buffer.appendThinking(messageId: "m", text: "thought", scheduleFlush: {})
    buffer.appendText(messageId: "m", text: String(repeating: "b", count: 10), scheduleFlush: {})

    XCTAssertTrue(buffer.flushPaced(messages: &messages))
    XCTAssertEqual(messages[0].contentBlocks.count, 1, "the thinking block waits for the text ahead of it")
    XCTAssertEqual(messages[0].text, String(repeating: "a", count: 22))

    buffer.flush(messages: &messages)
    XCTAssertEqual(messages[0].contentBlocks.count, 3)
    XCTAssertEqual(messages[0].text, String(repeating: "a", count: 100) + String(repeating: "b", count: 10))
  }

  func testAPacedFlushCutsOnCharacterBoundaries() {
    let buffer = ChatStreamingBuffer(flushInterval: 10)
    var messages = makeMessages()
    // Family emoji are one Character of several scalars; a cut must not split one.
    let text = String(repeating: "👨‍👩‍👧", count: 30)
    buffer.appendText(messageId: "m", text: text, scheduleFlush: {})

    _ = buffer.flushPaced(messages: &messages)
    XCTAssertEqual(messages[0].text, String(repeating: "👨‍👩‍👧", count: 6))
    buffer.flush(messages: &messages)
    XCTAssertEqual(messages[0].text, text)
  }

  func testTheRemainderReArmsItsOwnFlush() {
    let buffer = ChatStreamingBuffer(flushInterval: 0.01)
    var messages = makeMessages()
    let rearmed = expectation(description: "a paced flush that leaves text behind schedules the next")
    buffer.appendText(messageId: "m", text: String(repeating: "a", count: 100), scheduleFlush: {})

    XCTAssertTrue(buffer.flushPaced(messages: &messages))
    buffer.scheduleFlush { rearmed.fulfill() }

    wait(for: [rearmed], timeout: 1)
  }
}
