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
        XCTAssertTrue(instr.contains("manage_agent_pills"))
        XCTAssertTrue(instr.contains("list_agent_sessions"))
        XCTAssertTrue(instr.contains("get_agent_run"))
        XCTAssertTrue(instr.contains("cancel_agent_run"))
        XCTAssertTrue(instr.contains("floating agent pills"))
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
        XCTAssertTrue((statusTool?["description"] as? String ?? "").contains("floating agent pills"))
    }

    func testRealtimeAgentPillManagementToolIsExposed() {
        let tools = RealtimeHubTools.openAITools
        let manageTool = tools.first { ($0["name"] as? String) == HubTool.manageAgentPills.rawValue }
        XCTAssertNotNil(manageTool)
        XCTAssertTrue((manageTool?["description"] as? String ?? "").contains("dismiss"))
        XCTAssertTrue((manageTool?["description"] as? String ?? "").contains("clear completed"))
    }

    func testRealtimeCanonicalAgentControlToolsAreExposed() {
        let tools = RealtimeHubTools.openAITools
        let toolNames = Set(tools.compactMap { $0["name"] as? String })
        XCTAssertTrue(toolNames.contains(HubTool.listAgentSessions.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.getAgentRun.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.cancelAgentRun.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.inspectAgentArtifacts.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.updateAgentArtifactLifecycle.rawValue))

        let cancelTool = tools.first { ($0["name"] as? String) == HubTool.cancelAgentRun.rawValue }
        XCTAssertTrue((cancelTool?["description"] as? String ?? "").contains("canonical"))
        let cancelParameters = cancelTool?["parameters"] as? [String: Any]
        let cancelProperties = cancelParameters?["properties"] as? [String: Any]
        XCTAssertNotNil(cancelProperties?["agentRef"])
        XCTAssertNotNil(cancelParameters?["anyOf"])

        let listTool = tools.first { ($0["name"] as? String) == HubTool.listAgentSessions.rawValue }
        let listParameters = listTool?["parameters"] as? [String: Any]
        let listProperties = listParameters?["properties"] as? [String: Any]
        let surfaceKind = listProperties?["surfaceKind"] as? [String: Any]
        XCTAssertEqual(surfaceKind?["enum"] as? [String], ["main_chat", "task_chat", "realtime", "delegated_agent", "floating_pill"])

        let inspectTool = tools.first { ($0["name"] as? String) == HubTool.inspectAgentArtifacts.rawValue }
        let inspectParameters = inspectTool?["parameters"] as? [String: Any]
        let inspectAnyOf = inspectParameters?["anyOf"] as? [[String: Any]]
        XCTAssertEqual(
            inspectAnyOf?.compactMap { $0["required"] as? [String] },
            [["agentRef"], ["artifactRef"], ["artifactId"], ["sessionId"], ["runId"], ["attemptId"]]
        )
    }
}
