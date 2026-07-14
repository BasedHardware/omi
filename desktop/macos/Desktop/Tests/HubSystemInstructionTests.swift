import XCTest
@testable import Omi_Computer

final class HubSystemInstructionTests: XCTestCase {
    func testInstructionUsesExactKernelContextAndVoiceLanguagePresentation() {
        let kernelContext = "[Kernel Context Snapshot]\n{\"sourceOutcomes\":[{\"source\":\"identity\"}]}"
        let instr = RealtimeHubTools.systemInstruction(
            kernelContext: kernelContext,
            userLanguages: ["en"]
        )

        XCTAssertTrue(instr.contains(kernelContext))
        XCTAssertTrue(instr.lowercased().contains("language the user"))
        XCTAssertFalse(instr.contains("Always reply in English"))
        XCTAssertTrue(instr.contains(DesktopCapabilityRegistry.realtimeSelfModelPrompt))
        XCTAssertTrue(instr.contains("kernel makes the authoritative route"))
        XCTAssertTrue(instr.contains("image attached to its result"))
        XCTAssertTrue(instr.contains("source of truth for any current-screen question"))
    }

    func testLiveScreenshotResultSupersedesConflictingWarmScreenContext() {
        XCTAssertEqual(
            RealtimeHubTools.screenshotToolResult(capturedBytes: 1),
            "Live screenshot captured just now. The attached image is authoritative for the current screen; disregard any conflicting screen summaries, OCR, or earlier screen descriptions."
        )
        XCTAssertEqual(
            RealtimeHubTools.screenshotToolResult(capturedBytes: nil),
            "Could not capture the screen."
        )
    }

    func testInstructionDoesNotOwnSemanticSelectionOrRoutingPolicy() {
        let instr = RealtimeHubTools.systemInstruction()
        for forbidden in [
            "Try before asking",
            "Only ask a clarifying question",
            "Do not ask permission to delegate",
            "WHO the user is",
            "MOST RECENT exchange",
            "MUST call get_daily_recap",
            "rather than spawning an agent",
            "If the user asks to use/ask OpenClaw",
            "Resolve relative dates",
            "list_agent_sessions first",
            "Call ask_higher_model when",
            "spawn_agent proposes background work",
        ] {
            XCTAssertFalse(instr.contains(forbidden), "surface prompt must not own rule: \(forbidden)")
        }
    }

    func testInstructionKeepsOnlyGenericSpokenToolUseContractAroundGeneratedCapabilities() {
        let instr = RealtimeHubTools.systemInstruction()
        XCTAssertTrue(instr.contains("short spoken heads-up"))
        XCTAssertTrue(instr.contains("Never claim a physical action succeeded"))
        XCTAssertTrue(instr.contains("never read tool JSON or ids aloud"))
        XCTAssertTrue(instr.contains("spawn_agent"))
        XCTAssertTrue(instr.contains("check_permission_status"))
        XCTAssertTrue(instr.contains("request_permission"))
        XCTAssertFalse(instr.contains("run_agent_and_wait"))
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

    func testRealtimePermissionToolsAreExposedForDirectHandling() {
        let tools = RealtimeHubTools.openAITools
        let names = Set(tools.compactMap { $0["name"] as? String })
        XCTAssertTrue(names.contains(HubTool.checkPermissionStatus.rawValue))
        XCTAssertTrue(names.contains(HubTool.requestPermission.rawValue))

        let request = tools.first { ($0["name"] as? String) == HubTool.requestPermission.rawValue }
        let parameters = request?["parameters"] as? [String: Any]
        let properties = parameters?["properties"] as? [String: Any]
        XCTAssertNotNil(properties?["type"])
        XCTAssertTrue(
            (request?["description"] as? String ?? "").contains("kernel-authorized native executor")
        )
        XCTAssertFalse((request?["description"] as? String ?? "").contains("Never use spawn_agent"))
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
