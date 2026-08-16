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

  // MARK: - When the derivation runs

  /// Duplicate detection is a full pass over every long row in the mounted
  /// window — 4.2 ms at the 500-row cap, measured — and the transcript used to
  /// re-run it on every body evaluation, which during a streamed answer is once
  /// per 35 ms flush. A streamed tail cannot create a duplicate *pair* among the
  /// rows above it, so rewriting it must leave the derivation alone.
  func testRewritingTheStreamingTailDoesNotChangeTheDerivationKey() {
    let settled = [msg("1", sharedOpening + " settled answer")]
    let key = ChatTranscriptDuplicateKey(
      messages: settled + [msg("tail", "The answer so f")],
      presentation: .initial, conversationIdentity: "session", isSending: true)
    let afterMoreTokens = ChatTranscriptDuplicateKey(
      messages: settled + [msg("tail", "The answer so far, with a good deal more of it.")],
      presentation: .initial, conversationIdentity: "session", isSending: true)

    XCTAssertEqual(key, afterMoreTokens)
  }

  /// Everything that *can* introduce a duplicate, or change which rows are
  /// eligible to be one, must re-derive it.
  func testEveryChangeOfTranscriptShapeReDerivesTheDuplicates() {
    let messages = [msg("1", sharedOpening + " settled answer")]
    let base = ChatTranscriptDuplicateKey(
      messages: messages, presentation: .initial, conversationIdentity: "session", isSending: true)

    XCTAssertNotEqual(
      base,
      ChatTranscriptDuplicateKey(
        messages: messages + [msg("2", sharedOpening + " settled answer")],
        presentation: .initial, conversationIdentity: "session", isSending: true),
      "an arriving row is exactly how a duplicate appears")
    XCTAssertNotEqual(
      base,
      ChatTranscriptDuplicateKey(
        messages: messages, presentation: .expanded, conversationIdentity: "session",
        isSending: true),
      "expanding the window mounts rows that were not eligible before")
    XCTAssertNotEqual(
      base,
      ChatTranscriptDuplicateKey(
        messages: messages, presentation: .initial, conversationIdentity: "other",
        isSending: true),
      "another conversation's duplicates are not this one's")
    XCTAssertNotEqual(
      base,
      ChatTranscriptDuplicateKey(
        messages: messages, presentation: .initial, conversationIdentity: "session",
        isSending: false),
      "a settling turn may have had its text replaced wholesale by journal replay")
  }

  /// A prepend keeps the count moving, but "load earlier" can also replace the
  /// newest row on a surface that re-anchors — pin both halves of the identity.
  func testTheNewestRowIsPartOfTheShape() {
    XCTAssertNotEqual(
      ChatTranscriptDuplicateKey(
        messages: [msg("1", "a"), msg("2", "b")],
        presentation: .initial, conversationIdentity: "session", isSending: false),
      ChatTranscriptDuplicateKey(
        messages: [msg("1", "a"), msg("3", "b")],
        presentation: .initial, conversationIdentity: "session", isSending: false))
  }
}
