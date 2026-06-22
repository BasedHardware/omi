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
        XCTAssertTrue(instr.contains("get_task_agent_status"))
        XCTAssertTrue(instr.contains("subagents"))
        XCTAssertTrue(instr.contains("get_daily_recap"))
        XCTAssertTrue(instr.contains("ask_higher_model"))
        XCTAssertTrue(instr.contains("ANSWER YOURSELF"))
    }

    func testRealtimeToolSurfaceMatchesCapabilityRegistry() {
        let toolNames = Set(RealtimeHubTools.openAITools.compactMap { $0["name"] as? String })
        XCTAssertEqual(toolNames, Set(DesktopCapabilityRegistry.realtimeToolNames))
    }

    func testRealtimeTaskAgentStatusToolIsExposed() {
        let tools = RealtimeHubTools.openAITools
        let statusTool = tools.first { ($0["name"] as? String) == HubTool.getTaskAgentStatus.rawValue }
        XCTAssertNotNil(statusTool)
        XCTAssertTrue((statusTool?["description"] as? String ?? "").contains("subagents"))
    }
}
