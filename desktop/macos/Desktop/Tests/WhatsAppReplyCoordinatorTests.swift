import XCTest
@testable import Omi_Computer

final class WhatsAppReplyCoordinatorTests: XCTestCase {
    func testVisibleReplyTextRemovesReasoningParagraph() {
        let raw = """
        No clear context from memory. The message "6 pm" is likely a reply to a prior conversation about plans. I'll draft a simple, natural response acknowledging it.

        ok, 6 pm it is 👍
        """

        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: raw), "ok, 6 pm it is 👍")
    }

    func testVisibleReplyTextStripsReplyLabel() {
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: "Reply: Sounds good"), "Sounds good")
    }

    func testVisibleReplyTextStripsAlternateReplyLabels() {
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: "Draft reply: On my way"), "On my way")
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: "Message: See you soon"), "See you soon")
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: "WhatsApp reply: Thanks!"), "Thanks!")
    }

    func testVisibleReplyTextSingleLinePassthrough() {
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: "Sounds good to me"), "Sounds good to me")
    }

    func testVisibleReplyTextPreservesEmojiReply() {
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: "👍"), "👍")
        XCTAssertEqual(
            WhatsAppReplyCoordinator.visibleReplyText(from: "Reason: picking a reaction\n\n👍"),
            "👍"
        )
    }

    func testVisibleReplyTextStripsLineBasedReasoning() {
        let raw = """
        Context: prior plans were unclear.
        I'll draft a short confirmation.

        Yep, 6 pm works for me
        """
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: raw), "Yep, 6 pm works for me")
    }

    func testVisibleReplyTextStripsMultiParagraphReasoning() {
        let raw = """
        No clear context from memory.

        Based on the context, this looks like a scheduling follow-up.

        Perfect, see you at 6 👍
        """
        XCTAssertEqual(WhatsAppReplyCoordinator.visibleReplyText(from: raw), "Perfect, see you at 6 👍")
    }
}
