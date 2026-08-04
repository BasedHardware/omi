import XCTest

@testable import Omi_Computer

/// Regression coverage for `ChatMessageDeduplicator`. The transcript dedup used
/// to fingerprint each long message on only its first 200 characters, so two
/// genuinely distinct messages sharing an opening collided and the later one was
/// hidden from the chat. It now fingerprints on sender + the full body.
final class ChatMessageDeduplicatorTests: XCTestCase {

  private let sharedOpening = String(repeating: "a", count: 210)

  private func msg(_ id: String, _ text: String, _ sender: ChatSender = .ai) -> ChatMessage {
    ChatMessage(id: id, text: text, sender: sender)
  }

  func testDistinctLongMessagesSharingFirst200CharsAreNotCollapsed() {
    let messages = [
      msg("1", sharedOpening + " FIRST distinct ending"),
      msg("2", sharedOpening + " SECOND distinct ending"),
    ]
    // Before the fix both share the 200-'a' prefix and message 2 was flagged
    // as a duplicate and hidden. Now they are recognized as distinct.
    XCTAssertTrue(ChatMessageDeduplicator.duplicateIDs(in: messages).isEmpty)
  }

  func testExactWholeMessageDuplicateIsCollapsed() {
    let body = sharedOpening + " identical body"
    let messages = [msg("1", body), msg("2", body)]
    XCTAssertEqual(ChatMessageDeduplicator.duplicateIDs(in: messages), ["2"])
  }

  func testSameTextDifferentSenderIsNotADuplicate() {
    let body = sharedOpening + " same words"
    let messages = [msg("1", body, .user), msg("2", body, .ai)]
    XCTAssertTrue(ChatMessageDeduplicator.duplicateIDs(in: messages).isEmpty)
  }

  func testShortMessagesAreNeverDeduplicated() {
    let messages = [msg("1", "short repeated"), msg("2", "short repeated")]
    XCTAssertTrue(ChatMessageDeduplicator.duplicateIDs(in: messages).isEmpty)
  }

  func testVisibleDuplicateWorkIsBoundedToRecentTranscriptWindow() {
    let repeatedBody = sharedOpening + " repeated history body"
    let oldMessages = (0..<(ChatTranscriptWindow.maximumVisibleMessageCount * 20)).map { index in
      msg("old-\(index)", repeatedBody)
    }
    let visibleMessages = (0..<(ChatTranscriptWindow.maximumVisibleMessageCount - 1)).map { index in
      msg("visible-\(index)", "visible \(index)")
    }
    let visibleDuplicate = msg(
      "visible-duplicate",
      sharedOpening + " visible duplicate body"
    )
    let visibleDuplicateCopy = msg(
      "visible-duplicate-copy",
      sharedOpening + " visible duplicate body"
    )

    let duplicates = ChatTranscriptWindow.visibleDuplicateIDs(
      in: oldMessages + visibleMessages + [visibleDuplicate, visibleDuplicateCopy]
    )

    // The transcript renderer only displays the recent window, so streaming
    // body updates must not spend work deduplicating rows that cannot appear.
    XCTAssertEqual(duplicates, ["visible-duplicate-copy"])
  }
}
