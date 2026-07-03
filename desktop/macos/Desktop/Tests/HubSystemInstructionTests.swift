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

    func testLocalAgentProviderInstructionMatchesStrengthsToAvailability() {
        let availability = [
            LocalAgentProviderAvailability(provider: .openclaw, status: .available(command: "/usr/local/bin/openclaw")),
            LocalAgentProviderAvailability(provider: .hermes, status: .missing),
            LocalAgentProviderAvailability(provider: .codex, status: .available(command: "/usr/local/bin/codex-acp")),
        ]
        let instruction = RealtimeHubTools.localAgentProviderInstruction(availability: availability)

        // Available providers advertise their strengths for informed selection.
        XCTAssertTrue(instruction.contains("When the user does not name an agent, pick the provider whose strengths clearly match the task"))
        XCTAssertTrue(instruction.contains("OpenClaw: \(AgentPillsManager.DirectedProvider.openclaw.strengths)"))
        XCTAssertTrue(instruction.contains("Codex: \(AgentPillsManager.DirectedProvider.codex.strengths)"))
        // Unavailable providers must never be offered as a selection target.
        XCTAssertFalse(instruction.contains("Hermes: \(AgentPillsManager.DirectedProvider.hermes.strengths)"))
        XCTAssertTrue(instruction.contains("Hermes: not installed"))
        // Conservative defaults: explicit user mention always wins, and the
        // default agent remains the choice when no provider clearly matches.
        XCTAssertTrue(instruction.contains("omit provider to use Omi's default agent"))
        XCTAssertTrue(instruction.contains("When the user names an agent, always use that one."))
    }

    func testLocalAgentProviderInstructionOmitsStrengthsWhenNoneAvailable() {
        let availability = [
            LocalAgentProviderAvailability(provider: .openclaw, status: .missing),
            LocalAgentProviderAvailability(provider: .hermes, status: .missing),
            LocalAgentProviderAvailability(provider: .codex, status: .missing),
        ]
        let instruction = RealtimeHubTools.localAgentProviderInstruction(availability: availability)

        XCTAssertFalse(instruction.contains("When the user does not name an agent"))
        XCTAssertTrue(instruction.contains("do NOT spawn a default agent"))
    }

    func testLocalAgentProviderInstructionOffersInstallAssistOnConsent() {
        let availability = [
            LocalAgentProviderAvailability(provider: .openclaw, status: .available(command: "/usr/local/bin/openclaw")),
            LocalAgentProviderAvailability(provider: .hermes, status: .missing),
            LocalAgentProviderAvailability(provider: .codex, status: .missing),
        ]
        let instruction = RealtimeHubTools.localAgentProviderInstruction(availability: availability)

        // Unavailable branch: needs-setup stance is kept, install assist is
        // offered per missing provider, and the SINGLE shared consent rule
        // sentence gates the tool call.
        XCTAssertTrue(instruction.contains("do NOT spawn a default agent"))
        XCTAssertTrue(instruction.contains("Say it needs setup and offer to install it:"))
        XCTAssertTrue(instruction.contains("Hermes: not installed — offer to set it up via setup_agent_provider after explicit consent."))
        XCTAssertTrue(instruction.contains("Codex: not installed — offer to set it up via setup_agent_provider after explicit consent."))
        XCTAssertTrue(instruction.contains(LocalAgentProviderInstaller.consentRule))
        // Compact instruction fragments only: the full user-facing setup
        // prompt (install command + docs URL) stays on UI/toolError surfaces.
        XCTAssertFalse(instruction.contains(AgentPillsManager.DirectedProvider.hermes.installCommand))
        XCTAssertFalse(instruction.contains(AgentPillsManager.DirectedProvider.hermes.installDocsURL))
    }

    func testRealtimeSetupAgentProviderToolIsAlwaysExposedWithAllProviders() {
        // The tool stays in the schema even when every directed provider is
        // missing (or installed): the hub session's tool list is frozen at
        // session start, and the executor is idempotent for already-installed
        // providers, so an always-present tool is the simplest correct shape.
        let tools = RealtimeHubTools.openAITools(availableDirectedProviders: [])
        let setupTool = tools.first { ($0["name"] as? String) == HubTool.setupAgentProvider.rawValue }
        XCTAssertNotNil(setupTool)
        let description = (setupTool?["description"] as? String) ?? ""
        XCTAssertTrue(description.contains(LocalAgentProviderInstaller.consentRule))
        XCTAssertTrue(description.contains("native confirmation dialog"))
        XCTAssertTrue(description.contains("nothing downloads or runs until they click Install"))

        let parameters = setupTool?["parameters"] as? [String: Any]
        let properties = parameters?["properties"] as? [String: Any]
        let provider = properties?["provider"] as? [String: Any]
        XCTAssertEqual(provider?["enum"] as? [String], ["openclaw", "hermes", "codex"])
        XCTAssertEqual(parameters?["required"] as? [String], ["provider"])
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
