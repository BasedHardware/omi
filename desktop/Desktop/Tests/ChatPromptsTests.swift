import XCTest
@testable import Omi_Computer

final class ChatPromptsTests: XCTestCase {
    func testOnboardingDefersWebResearchUntilAfterFileScanAndEmailAttempt() throws {
        let prompt = ChatPromptBuilder.buildOnboardingChat(
            userName: "Taylor Swift",
            givenName: "Taylor",
            email: "taylor@example.com"
        )

        let step2Range = try XCTUnwrap(prompt.range(of: "STEP 2 — MONTHLY GOAL (BEFORE SCAN)"))
        let step3Range = try XCTUnwrap(prompt.range(of: "STEP 3 — FILE SCAN (AFTER GOAL)"))
        let step4Range = try XCTUnwrap(prompt.range(of: "STEP 4 — FILE DISCOVERIES + TASK CANDIDATES"))
        let step5Range = try XCTUnwrap(prompt.range(of: "STEP 5 — WEB RESEARCH (ONLY AFTER FILES + EMAIL ATTEMPT)"))
        let gateRange = try XCTUnwrap(
            prompt.range(
                of: "Only do web research AFTER the user has shared file access via `scan_files` and AFTER Omi has already attempted to read recent Gmail in the background."
            )
        )

        XCTAssertLessThan(step2Range.lowerBound, step3Range.lowerBound)
        XCTAssertLessThan(step3Range.lowerBound, step4Range.lowerBound)
        XCTAssertLessThan(step4Range.lowerBound, step5Range.lowerBound)
        XCTAssertGreaterThan(gateRange.lowerBound, step5Range.lowerBound)
    }
}
