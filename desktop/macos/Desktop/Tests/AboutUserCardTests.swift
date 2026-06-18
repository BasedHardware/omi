import XCTest
@testable import Omi_Computer

final class AboutUserCardTests: XCTestCase {
    func testRenderIncludesNameFactsCountsAndHedge() {
        let card = AboutUserCard.render(
            name: "Sam",
            facts: ["Lives in San Francisco", "Prefers concise answers"],
            overdue: 2,
            dueToday: 3
        )
        XCTAssertTrue(card.contains("<about_user>"))
        XCTAssertTrue(card.contains("</about_user>"))
        XCTAssertTrue(card.contains("Name: Sam"))
        XCTAssertTrue(card.contains("- Lives in San Francisco"))
        XCTAssertTrue(card.contains("- Prefers concise answers"))
        XCTAssertTrue(card.contains("2 overdue"))
        XCTAssertTrue(card.contains("3 due today"))
        XCTAssertTrue(card.contains("snapshot"))
    }

    func testRenderEmptyState() {
        let card = AboutUserCard.render(name: "", facts: [], overdue: 0, dueToday: 0)
        XCTAssertFalse(card.contains("Name:"))                 // no name line when empty
        XCTAssertTrue(card.contains("Nothing saved"))          // facts empty-state
        XCTAssertTrue(card.contains("nothing overdue or due today"))
    }
}
