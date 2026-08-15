import XCTest

@testable import Omi_Computer

final class ConversationShareLinkActionTests: XCTestCase {
  @MainActor
  func testSuccessfulMintCopiesTheMintedLinkExactly() async {
    var copied: [String] = []
    let feedback = await ConversationShareLinkAction.run(
      mintLink: { "https://h.omi.me/conversations/abc" },
      copyToPasteboard: { link in
        copied.append(link)
        return true
      }
    )
    XCTAssertEqual(feedback, .copied)
    XCTAssertEqual(copied, ["https://h.omi.me/conversations/abc"])
  }

  @MainActor
  func testRejectedPasteboardWriteIsNotReportedAsCopied() async {
    let feedback = await ConversationShareLinkAction.run(
      mintLink: { "https://h.omi.me/conversations/abc" },
      copyToPasteboard: { _ in false }
    )
    XCTAssertEqual(feedback, .failed)
  }

  @MainActor
  func testFailedMintCopiesNothingAndReportsTheError() async {
    struct MintError: Error {}
    var copied: [String] = []
    var reportedErrors = 0
    let feedback = await ConversationShareLinkAction.run(
      mintLink: { throw MintError() },
      copyToPasteboard: { link in
        copied.append(link)
        return true
      },
      onFailure: { _ in reportedErrors += 1 }
    )
    XCTAssertEqual(feedback, .failed)
    // Minting is the visibility mutation that makes the URL work; after a
    // failure the user must not be handed a link presented as usable.
    XCTAssertTrue(copied.isEmpty)
    XCTAssertEqual(reportedErrors, 1)
  }

  func testCopiedConfirmationDisclosesTheLinkAudience() {
    // getConversationShareLink flips the conversation's visibility to
    // "shared" before returning the URL, so the confirmation must disclose
    // the audience instead of reading as a plain clipboard copy.
    XCTAssertTrue(ConversationShareLinkFeedback.copied.message.contains("anyone with the link"))
    XCTAssertEqual(ConversationShareLinkFeedback.failed.message, "Couldn't create link")
  }

  func testCopyLinkRichBlockActionStaysInsideTheClosedSchema() {
    XCTAssertEqual(ChatFirstAnalyticsEvent.RichBlockAction.copyLink.rawValue, "copy_link")
    let payload = ChatFirstAnalyticsEvent.richBlock(
      kind: .conversationLink,
      outcome: .acted,
      action: .copyLink
    ).analyticsPayload
    XCTAssertEqual(payload.eventName, "chat_first_rich_block")
    XCTAssertEqual(payload.properties["action"], "copy_link")
    XCTAssertEqual(
      Set(payload.properties.keys),
      ["kind", "outcome", "action", "telemetry_schema_version"]
    )
  }
}
