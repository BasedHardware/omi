import XCTest
@testable import Omi_Computer

final class HubSystemInstructionTests: XCTestCase {
    func testInstructionInjectsCardAndUsesUserLanguage() {
        let card = "<about_user>\nName: Sam\n</about_user>"
        let instr = RealtimeHubTools.systemInstruction(aboutUser: card)
        XCTAssertTrue(instr.contains(card))                                   // card injected
        XCTAssertTrue(instr.lowercased().contains("language the user"))        // reply-in-user-language
        XCTAssertFalse(instr.contains("Always reply in English"))             // old rule gone
        XCTAssertTrue(instr.contains("spawn_agent"))
        XCTAssertTrue(instr.contains("list_agent_sessions"))
        XCTAssertFalse(instr.contains("run_agent_and_wait"))
        XCTAssertTrue(instr.contains("set_desktop_attention_override"))
        XCTAssertTrue(instr.contains("get_agent_run"))
        XCTAssertTrue(instr.contains("cancel_agent_run"))
        XCTAssertTrue(instr.contains("floating-bar pill projections"))
        XCTAssertTrue(instr.contains("subagent"))
        XCTAssertTrue(instr.contains("get_daily_recap"))
        XCTAssertTrue(instr.contains("ask_higher_model"))
        XCTAssertTrue(instr.contains("create_calendar_event"))
        XCTAssertTrue(instr.contains("Current local datetime:"))
        XCTAssertTrue(instr.contains("Current timezone:"))
        XCTAssertTrue(instr.contains("Resolve relative dates"))
        XCTAssertTrue(instr.contains("ANSWER YOURSELF"))
    }

    func testInstructionRequiresTryingContextBeforeAsking() {
        let instr = RealtimeHubTools.systemInstruction(aboutUser: "")
        XCTAssertTrue(instr.contains("Try before asking"))
        XCTAssertTrue(instr.contains("use the relevant read tools before asking the user"))
        XCTAssertTrue(instr.contains("Missing or incomplete context is"))
        XCTAssertTrue(instr.contains("not a reason to ask first"))
        XCTAssertTrue(instr.contains("give the best answer you can with a confidence caveat"))
    }

    func testInstructionDelegatesLargerVoiceWork() {
        let instr = RealtimeHubTools.systemInstruction(aboutUser: "")
        XCTAssertTrue(instr.contains("Larger work"))
        XCTAssertTrue(instr.contains("PTT is the fast front door"))
        XCTAssertTrue(instr.contains("call spawn_agent with a clear objective and title"))
        XCTAssertTrue(instr.contains("Do not ask permission to delegate when the user's intent is clear"))
        XCTAssertTrue(instr.contains("work product, investigation, or"))
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

    func testRealtimeListAgentSessionsToolIsExposed() {
        let tools = RealtimeHubTools.openAITools
        let listTool = tools.first { ($0["name"] as? String) == HubTool.listAgentSessions.rawValue }
        XCTAssertNotNil(listTool)
        XCTAssertTrue((listTool?["description"] as? String ?? "").contains("subagents"))
        XCTAssertTrue((listTool?["description"] as? String ?? "").contains("floating"))
    }

    func testRealtimeAttentionOverrideToolIsExposed() {
        let tools = RealtimeHubTools.openAITools
        let overrideTool = tools.first { ($0["name"] as? String) == HubTool.setDesktopAttentionOverride.rawValue }
        XCTAssertNotNil(overrideTool)
        XCTAssertTrue((overrideTool?["description"] as? String ?? "").contains("dismiss"))
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

    func testGeminiRealtimeToolSchemasOmitUnsupportedJsonSchemaKeys() {
        let declarations = RealtimeHubTools.geminiFunctionDeclarations
        XCTAssertFalse(declarations.isEmpty)

        func assertGeminiSchemaClean(_ schema: [String: Any], path: String) {
            for key in schema.keys {
                XCTAssertFalse(
                    ["additionalProperties", "$schema", "const"].contains(key),
                    "unsupported key \(key) at \(path)")
            }
            if let type = schema["type"] as? String {
                XCTAssertEqual(type, type.uppercased(), "type must be uppercase at \(path)")
            }
            if let props = schema["properties"] as? [String: Any] {
                for (name, value) in props {
                    if let nested = value as? [String: Any] {
                        assertGeminiSchemaClean(nested, path: "\(path).properties.\(name)")
                    }
                }
            }
            if let items = schema["items"] as? [String: Any] {
                assertGeminiSchemaClean(items, path: "\(path).items")
            }
        }

        for decl in declarations {
            let name = decl["name"] as? String ?? "<unknown>"
            guard let parameters = decl["parameters"] as? [String: Any] else {
                XCTFail("missing parameters for \(name)")
                continue
            }
            assertGeminiSchemaClean(parameters, path: name)
        }
    }

    func testRealtimeCanonicalAgentControlToolsAreExposed() {
        let tools = RealtimeHubTools.openAITools
        let toolNames = Set(tools.compactMap { $0["name"] as? String })
        XCTAssertTrue(toolNames.contains(HubTool.listAgentSessions.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.getAgentRun.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.cancelAgentRun.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.inspectAgentArtifacts.rawValue))
        XCTAssertTrue(toolNames.contains(HubTool.updateAgentArtifactLifecycle.rawValue))
        XCTAssertFalse(toolNames.contains("run_agent_and_wait"))

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
        XCTAssertEqual(surfaceKind?["enum"] as? [String], ["main_chat", "task_chat", "realtime", "delegated_agent", "background_agent", "floating_bar", "floating_pill"])

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
