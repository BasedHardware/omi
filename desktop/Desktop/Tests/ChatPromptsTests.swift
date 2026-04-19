import XCTest
@testable import Omi_Computer

final class ChatPromptsTests: XCTestCase {
    func testOnboardingDefersWebResearchUntilAfterFileScanAndEmailAttempt() throws {
        let prompt = ChatPromptBuilder.buildOnboardingChat(
            userName: "Taylor Swift",
            givenName: "Taylor",
            email: "taylor@example.com"
        )

        let step2Range = try XCTUnwrap(prompt.range(of: "STEP 2 — FILE SCAN + EMAIL READING"))
        let step3Range = try XCTUnwrap(prompt.range(of: "STEP 3 — NON-RESTART PERMISSIONS"))
        let step4Range = try XCTUnwrap(prompt.range(of: "STEP 4 — WEB RESEARCH"))
        let step5Range = try XCTUnwrap(prompt.range(of: "STEP 5 — SCREEN RECORDING"))
        let step6Range = try XCTUnwrap(prompt.range(of: "STEP 6 — EMAIL INSIGHTS + MONTHLY GOAL"))
        let gateRange = try XCTUnwrap(
            prompt.range(
                of: "Use what you learned from the file scan to make the searches more targeted."
            )
        )

        XCTAssertLessThan(step2Range.lowerBound, step3Range.lowerBound)
        XCTAssertLessThan(step3Range.lowerBound, step4Range.lowerBound)
        XCTAssertLessThan(step4Range.lowerBound, step5Range.lowerBound)
        XCTAssertLessThan(step5Range.lowerBound, step6Range.lowerBound)
        XCTAssertGreaterThan(gateRange.lowerBound, step4Range.lowerBound)
        XCTAssertLessThan(gateRange.lowerBound, step5Range.lowerBound)
    }
}
