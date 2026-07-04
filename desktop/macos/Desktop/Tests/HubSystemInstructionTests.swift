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
        XCTAssertTrue(instr.contains("create_calendar_event"))
        XCTAssertTrue(instr.contains("Current local datetime:"))
        XCTAssertTrue(instr.contains("Current timezone:"))
        XCTAssertTrue(instr.contains("Resolve relative dates"))
        XCTAssertTrue(instr.contains("ANSWER YOURSELF"))
    }

    func testRealtimeToolSurfaceMatchesCapabilityRegistry() {
        let toolNames = Set(RealtimeHubTools.openAITools.compactMap { $0["name"] as? String })
        XCTAssertEqual(toolNames, Set(DesktopCapabilityRegistry.realtimeToolNames))
    }

    func testRealtimeSpawnAgentProviderEnumOnlyAdvertisesAvailableProviders() {
        let tools = RealtimeHubTools.openAITools(availableDirectedProviders: ["openclaw"])
        let spawnAgent = tools.first { ($0["name"] as? String) == HubTool.spawnAgent.rawValue }
        let parameters = spawnAgent?["parameters"] as? [String: Any]
        let properties = parameters?["properties"] as? [String: Any]
        let provider = properties?["provider"] as? [String: Any]

        XCTAssertEqual(provider?["enum"] as? [String], ["openclaw"])
    }

    func testRealtimeSpawnAgentOmitsProviderWhenNoLocalProvidersAreAvailable() {
        let tools = RealtimeHubTools.openAITools(availableDirectedProviders: [])
        let spawnAgent = tools.first { ($0["name"] as? String) == HubTool.spawnAgent.rawValue }
        let parameters = spawnAgent?["parameters"] as? [String: Any]
        let properties = parameters?["properties"] as? [String: Any]

        XCTAssertNil(properties?["provider"])
        XCTAssertNotNil(properties?["brief"])
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
        XCTAssertTrue((manageTool?["description"] as? String ?? "").contains("clear pills"))
        XCTAssertTrue((manageTool?["description"] as? String ?? "").contains("explicitly asks"))
        XCTAssertTrue((manageTool?["description"] as? String ?? "").contains("Never dismiss completed agents"))
    }

    func testRealtimeCreateCalendarEventToolIsExposedWithRequiredArguments() {
        let tools = RealtimeHubTools.openAITools
        let calendarTool = tools.first { ($0["name"] as? String) == HubTool.createCalendarEvent.rawValue }
        XCTAssertNotNil(calendarTool)
        XCTAssertTrue((calendarTool?["description"] as? String ?? "").contains("Google Calendar"))

        let parameters = calendarTool?["parameters"] as? [String: Any]
        let properties = parameters?["properties"] as? [String: Any]
        XCTAssertNotNil(properties?["title"])
        XCTAssertNotNil(properties?["start_time"])
        XCTAssertNotNil(properties?["end_time"])
        XCTAssertNotNil(properties?["attendees"])
        XCTAssertEqual(parameters?["required"] as? [String], ["title", "start_time", "end_time"])
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
        // Schemas must stay flat (no root-level anyOf) for provider compatibility.
        XCTAssertNil(cancelParameters?["anyOf"])

        let listTool = tools.first { ($0["name"] as? String) == HubTool.listAgentSessions.rawValue }
        let listParameters = listTool?["parameters"] as? [String: Any]
        let listProperties = listParameters?["properties"] as? [String: Any]
        let surfaceKind = listProperties?["surfaceKind"] as? [String: Any]
        XCTAssertEqual(surfaceKind?["enum"] as? [String], ["main_chat", "task_chat", "realtime", "delegated_agent", "background_agent", "floating_pill"])

        let inspectTool = tools.first { ($0["name"] as? String) == HubTool.inspectAgentArtifacts.rawValue }
        let inspectParameters = (inspectTool?["parameters"] as? [String: Any])
        XCTAssertNotNil(inspectParameters, "inspect_agent_artifacts must declare a parameters object")
        let inspectProperties = inspectParameters?["properties"] as? [String: Any]
        XCTAssertNotNil(inspectProperties?["agentRef"], "inspect_agent_artifacts must expose an agentRef property")
        XCTAssertNotNil(inspectProperties?["artifactRef"], "inspect_agent_artifacts must expose an artifactRef property")
        XCTAssertNotNil(inspectProperties?["artifactId"], "inspect_agent_artifacts must expose an artifactId property")
        XCTAssertNotNil(inspectProperties?["sessionId"], "inspect_agent_artifacts must expose a sessionId property")
        XCTAssertNotNil(inspectProperties?["runId"], "inspect_agent_artifacts must expose a runId property")
        XCTAssertNotNil(inspectProperties?["attemptId"], "inspect_agent_artifacts must expose an attemptId property")
        // Schemas must stay flat (no root-level anyOf) for provider compatibility.
        XCTAssertNil(inspectParameters?["anyOf"])
    }
}
