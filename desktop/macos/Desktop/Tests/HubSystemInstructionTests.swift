import XCTest
@testable import Omi_Computer

final class HubSystemInstructionTests: XCTestCase {
    func testInstructionInjectsCardAndUsesUserLanguage() {
        let card = "<about_user>\nName: Sam\n</about_user>"
        let instr = RealtimeHubTools.systemInstruction(aboutUser: card)
        XCTAssertTrue(instr.contains(card))                                   // card injected
        XCTAssertTrue(instr.lowercased().contains("language the user"))        // reply-in-user-language
        XCTAssertFalse(instr.contains("Always reply in English"))             // old rule gone
        XCTAssertTrue(instr.contains("spawn_agent"))                          // guardrails preserved
        XCTAssertTrue(instr.contains("get_daily_recap"))
    }
}
