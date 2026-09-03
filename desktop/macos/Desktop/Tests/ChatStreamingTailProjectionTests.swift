import XCTest

@testable import Omi_Computer

/// The streaming buffer must never feed a withholding projection its own output.
///
/// `normalizeStreamingAssistantText` withholds the follow-up tail so the chip's
/// words never appear as prose. That is only sound while the projection sees the
/// whole raw answer on every flush: written back into the message, the withheld
/// delimiter is gone by the next flush and the question leaks a token at a time.
@MainActor
final class ChatStreamingTailProjectionTests: XCTestCase {
  private let answer = "Kubernetes reschedules the pod on the surviving node."
  private let tail = " <<<FOLLOWUP>>> Want the eviction timeline for that node?"

  private func normalize(_ message: ChatMessage, _ text: String) -> String {
    guard message.sender == .ai else { return text }
    return ChatProvider.normalizeStreamingAssistantText(text)
  }

  /// Replay the same stream broken at every possible flush boundary.
  func testNoFlushBoundaryLeaksAnyPartOfTheTail() {
    let stream = Array(answer + tail)

    for boundary in 1..<stream.count {
      let messageId = "assistant-\(boundary)"
      var messages = [ChatMessage(id: messageId, text: "", sender: .ai, isStreaming: true)]
      let buffer = ChatStreamingBuffer(flushInterval: 0.1)

      let first = String(stream[0..<boundary])
      let second = String(stream[boundary...])

      buffer.appendText(messageId: messageId, text: first, scheduleFlush: {})
      buffer.flush(messages: &messages, normalizeText: normalize)
      let afterFirst = messages[0].text

      buffer.appendText(messageId: messageId, text: second, scheduleFlush: {})
      buffer.flush(messages: &messages, normalizeText: normalize)
      let afterSecond = messages[0].text

      for visible in [afterFirst, afterSecond] {
        XCTAssertFalse(
          visible.contains("FOLLOWUP"),
          "boundary \(boundary) leaked the marker: \(visible)")
        XCTAssertFalse(
          visible.contains("eviction"),
          "boundary \(boundary) leaked the question: \(visible)")
        XCTAssertFalse(
          visible.contains("<<<"),
          "boundary \(boundary) leaked a partial marker: \(visible)")
      }
      XCTAssertEqual(
        afterSecond.trimmingCharacters(in: .whitespaces), answer,
        "boundary \(boundary) did not settle on the answer alone")
    }
  }

  /// Token-at-a-time delivery, which is what the transport actually does.
  func testCharacterByCharacterStreamNeverLeaksTheTail() {
    let messageId = "assistant-chars"
    var messages = [ChatMessage(id: messageId, text: "", sender: .ai, isStreaming: true)]
    let buffer = ChatStreamingBuffer(flushInterval: 0.1)

    for character in answer + tail {
      buffer.appendText(messageId: messageId, text: String(character), scheduleFlush: {})
      buffer.flush(messages: &messages, normalizeText: normalize)
      XCTAssertFalse(messages[0].text.contains("FOLLOWUP"))
      XCTAssertFalse(messages[0].text.contains("eviction"))
    }

    XCTAssertEqual(messages[0].text.trimmingCharacters(in: .whitespaces), answer)
    guard case .text(_, let blockText) = messages[0].contentBlocks[0] else {
      return XCTFail("Expected one text block")
    }
    XCTAssertFalse(blockText.contains("eviction"), "the trailing text block leaked the question")
  }

  /// The accumulator is per turn: a released id starts clean, not from the last answer.
  func testFinishStreamingReleasesTheTurnsAccumulator() {
    let messageId = "assistant-reused"
    var messages = [ChatMessage(id: messageId, text: "", sender: .ai, isStreaming: true)]
    let buffer = ChatStreamingBuffer(flushInterval: 0.1)

    buffer.appendText(messageId: messageId, text: "First answer.", scheduleFlush: {})
    buffer.flush(messages: &messages, normalizeText: normalize)
    buffer.finishStreaming(messageId: messageId)

    messages[0].text = ""
    messages[0].contentBlocks = []
    buffer.appendText(messageId: messageId, text: "Second answer.", scheduleFlush: {})
    buffer.flush(messages: &messages, normalizeText: normalize)

    XCTAssertEqual(messages[0].text, "Second answer.")
  }
}
