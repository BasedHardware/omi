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
}
