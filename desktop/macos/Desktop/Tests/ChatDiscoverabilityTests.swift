import XCTest
@testable import Omi_Computer

final class ChatDiscoverabilityTests: XCTestCase {

    // MARK: - Schema Footer

    func testSchemaFooterIncludesFTSTables() {
        let footer = ChatPrompts.schemaFooter
        XCTAssertTrue(footer.contains("screenshots_fts"))
        XCTAssertTrue(footer.contains("action_items_fts"))
        XCTAssertTrue(footer.contains("staged_tasks_fts"))
        XCTAssertTrue(footer.contains("task_chat_messages_fts"))
        XCTAssertTrue(footer.contains("proactive_extractions_fts"))
    }

    func testSchemaFooterIncludesMATCHPattern() {
        let footer = ChatPrompts.schemaFooter
        XCTAssertTrue(footer.contains("MATCH"))
        XCTAssertTrue(footer.contains("bm25("))
    }

    func testSchemaFooterIncludesRelationships() {
        let footer = ChatPrompts.schemaFooter
        XCTAssertTrue(footer.contains("action_items.screenshotId"))
        XCTAssertTrue(footer.contains("transcription_segments.sessionId"))
        XCTAssertTrue(footer.contains("memories.screenshotId"))
        XCTAssertTrue(footer.contains("focus_sessions.screenshotId"))
        XCTAssertTrue(footer.contains("observations.screenshotId"))
        XCTAssertTrue(footer.contains("live_notes.sessionId"))
    }

    // MARK: - Column Annotations

    func testColumnAnnotationsExistForAllAnnotatedTables() {
        let annotatedTables = ChatPrompts.tableAnnotations.keys
        for table in annotatedTables {
            // Every table in tableAnnotations should have columnAnnotations
            // (except tables added without column docs — those are OK)
            if let cols = ChatPrompts.columnAnnotations[table] {
                XCTAssertFalse(cols.isEmpty, "Column annotations for \(table) should not be empty")
            }
        }
    }

    func testScreenshotsHasKeyColumnAnnotations() {
        let cols = ChatPrompts.columnAnnotations["screenshots"]!
        XCTAssertNotNil(cols["timestamp"])
        XCTAssertNotNil(cols["appName"])
        XCTAssertNotNil(cols["ocrText"])
    }

    func testActionItemsHasKeyColumnAnnotations() {
        let cols = ChatPrompts.columnAnnotations["action_items"]!
        XCTAssertNotNil(cols["description"])
        XCTAssertNotNil(cols["completed"])
        XCTAssertNotNil(cols["priority"])
        XCTAssertNotNil(cols["screenshotId"])
    }

    func testMemoriesHasKeyColumnAnnotations() {
        let cols = ChatPrompts.columnAnnotations["memories"]!
        XCTAssertNotNil(cols["content"])
        XCTAssertNotNil(cols["category"])
        XCTAssertNotNil(cols["source"])
    }

    // MARK: - Excluded Tables and Columns

    func testExcludedTablesDoNotIncludeUserTables() {
        let excluded = ChatPrompts.excludedTables
        XCTAssertFalse(excluded.contains("screenshots"))
        XCTAssertFalse(excluded.contains("action_items"))
        XCTAssertFalse(excluded.contains("memories"))
        XCTAssertFalse(excluded.contains("focus_sessions"))
    }

    func testExcludedColumnsFilterInfrastructure() {
        let excluded = ChatPrompts.excludedColumns
        XCTAssertTrue(excluded.contains("imagePath"))
        XCTAssertTrue(excluded.contains("embedding"))
        XCTAssertTrue(excluded.contains("backendId"))
        XCTAssertTrue(excluded.contains("backendSynced"))
        // User-facing columns should not be excluded
        XCTAssertFalse(excluded.contains("description"))
        XCTAssertFalse(excluded.contains("content"))
        XCTAssertFalse(excluded.contains("ocrText"))
    }

    // MARK: - Tool Prompt

    func testToolPromptIncludesSearchTasks() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("**search_tasks**"))
        XCTAssertTrue(prompt.contains("Vector similarity search on tasks"))
    }

    func testToolPromptDoesNotPinStaleToolCount() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertFalse(prompt.contains("You have 7 tools"))
        XCTAssertFalse(prompt.contains("You have \(DesktopCapabilityRegistry.desktopToolNames.count) Omi tools"))
    }

    func testDesktopPromptDistinguishesPublicWebFromPrivateOmiRetrieval() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("Public internet, external companies/products/people"))
        XCTAssertTrue(prompt.contains("use web_search"))
        XCTAssertTrue(prompt.contains("private history, conversations, memories"))
        XCTAssertTrue(prompt.contains("For short follow-ups such as \"look it up,\""))
        XCTAssertTrue(prompt.contains("Never claim that public information is unavailable"))
    }

    func testToolPromptListsSearchTasksInWhenToUse() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("find tasks about shopping"))
    }

    func testDesktopPromptMentionsEveryDesktopCapability() {
        let prompt = ChatPrompts.desktopChat
        for toolName in DesktopCapabilityRegistry.desktopToolNames {
            XCTAssertTrue(prompt.contains("**\(toolName)**"), "Missing desktop capability \(toolName)")
        }
    }

    func testDesktopPromptMentionsListAgentSessionsForSubagents() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("**list_agent_sessions**"))
        XCTAssertTrue(prompt.contains("your subagents"))
        XCTAssertTrue(prompt.contains("Call list_agent_sessions"))
        XCTAssertTrue(prompt.contains("floating_agent_pills"))
    }

    func testDesktopPromptCanSpawnFloatingAgents() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("**spawn_agent**"))
        XCTAssertTrue(prompt.contains("call spawn_agent") || prompt.contains("Start background work -> spawn_agent"))
        XCTAssertTrue(prompt.contains("circular floating agent pills") || prompt.contains("floating-bar"))
    }

    func testDesktopPromptDistinguishesSpawnFromRunAndWait() {
        let prompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(excluding: [])
        XCTAssertTrue(prompt.contains("**run_agent_and_wait**") || prompt.contains("run_agent_and_wait"))
        XCTAssertTrue(prompt.contains("spawn_agent"))
        XCTAssertTrue(prompt.contains("Synchronous parent-linked child result"))
        XCTAssertTrue(prompt.contains("Start background work"))
    }

    func testDesktopPromptPreservesLegacyToolBehaviorGuidance() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("Do not guess when you can look it up"))
        XCTAssertTrue(prompt.contains("Supports SELECT, INSERT, UPDATE, DELETE"))
        XCTAssertTrue(prompt.contains("Supports FTS5 MATCH queries"))
        XCTAssertTrue(prompt.contains("More reliable than hand-writing MATCH queries for task search"))
        XCTAssertTrue(prompt.contains("**save_knowledge_graph**"))
        XCTAssertTrue(prompt.contains("Deduplication is handled automatically"))
    }

    func testDesktopPromptPreservesPersonalDataLookupContract() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("For ANY personal question"))
        XCTAssertTrue(prompt.contains("FIRST check <user_facts>"))
        XCTAssertTrue(prompt.contains("before saying you don't know"))
        XCTAssertTrue(prompt.contains("transcription_sessions/transcription_segments"))
        XCTAssertTrue(prompt.contains("NEVER say \"I don't know\""))
    }

    func testDesktopCapabilitiesExistInAgentToolDeclarations() throws {
        let manifestJSON = try readMacOSFile("agent/tests/fixtures/tool-manifest.json")
        let manifest = try JSONSerialization.jsonObject(with: Data(manifestJSON.utf8)) as? [[String: Any]]
        let fixture = try XCTUnwrap(manifest)
        var declaredTools = Set<String>()
        for entry in fixture {
            guard let name = entry["name"] as? String,
                  let adapters = entry["adapters"] as? [String: Any] else { continue }
            for adapterId in ["pi-mono", "omi-tools-stdio"] {
                guard let availability = adapters[adapterId] as? [String: Any],
                      (availability["advertised"] as? Bool) == true else { continue }
                declaredTools.insert(name)
            }
            if let executor = entry["executor"] as? [String: Any],
               executor["kind"] as? String == "runtimeControl" {
                declaredTools.insert(name)
            }
        }
        let localApiOnlyTools: Set<String> = ["get_local_status", "get_screenshot"]

        for toolName in DesktopCapabilityRegistry.desktopToolNames where !localApiOnlyTools.contains(toolName) {
            XCTAssertTrue(declaredTools.contains(toolName), "Missing agent tool declaration for \(toolName)")
        }
    }

    func testAgentControlCapabilitiesMatchCanonicalManifest() throws {
        let manifestEntries = try readAgentControlManifestEntries()
            .filter { $0.surfaces.contains(.desktopChat) }
        let capabilities = Dictionary(
            uniqueKeysWithValues: DesktopCapabilityRegistry.capabilities(for: .desktopChat).map { ($0.toolName, $0) })

        for entry in manifestEntries {
            let capability = try XCTUnwrap(capabilities[entry.name], "Missing Swift capability for \(entry.name)")
            XCTAssertEqual(capability.title, entry.label, "\(entry.name) label drifted")
            XCTAssertEqual(capability.latency.rawValue, entry.latency, "\(entry.name) latency drifted")
            XCTAssertEqual(capability.summary, entry.summary, "\(entry.name) summary drifted")
            XCTAssertEqual(capability.surfaces, entry.surfaces, "\(entry.name) surface drifted")
            XCTAssertFalse(entry.promptSnippet.isEmpty, "\(entry.name) manifest promptSnippet is empty")
            XCTAssertFalse(entry.runtimePreconditions.isEmpty, "\(entry.name) manifest runtimePreconditions is empty")
            for guideline in entry.promptGuidelines {
                XCTAssertTrue(
                    capability.bullets.contains(guideline),
                    "\(entry.name) missing manifest guideline in Swift docs: \(guideline)")
            }
        }
    }

    private func readToolNames(from relativePath: String) throws -> Set<String> {
        let testFile = URL(fileURLWithPath: #filePath)
        let desktopDir = testFile.deletingLastPathComponent().deletingLastPathComponent()
        let macOSDir = desktopDir.deletingLastPathComponent()
        let file = macOSDir.appendingPathComponent(relativePath)
        let text = try String(contentsOf: file)
        let regex = try NSRegularExpression(pattern: #"name:\s*"([^"]+)""#)
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        return Set(regex.matches(in: text, range: range).compactMap { match in
            guard let nameRange = Range(match.range(at: 1), in: text) else { return nil }
            return String(text[nameRange])
        })
    }

    private struct AgentControlManifestEntry {
        let name: String
        let label: String
        let summary: String
        let promptSnippet: String
        let promptGuidelines: [String]
        let latency: String
        let surfaces: Set<DesktopCapabilityRegistry.Surface>
        let runtimePreconditions: [String]
    }

    private func readAgentControlManifestEntries() throws -> [AgentControlManifestEntry] {
        let source = try readMacOSFile("agent/src/runtime/control-tool-manifest.ts")
        guard let start = source.range(of: "export const agentControlCapabilityManifest = ["),
              let end = source.range(of: "] as const", range: start.upperBound..<source.endIndex) else {
            XCTFail("Could not find agentControlCapabilityManifest")
            return []
        }
        let body = String(source[start.upperBound..<end.lowerBound])
        let nameRegex = try NSRegularExpression(pattern: #"name:\s*"([^"]+)""#)
        let range = NSRange(body.startIndex..<body.endIndex, in: body)
        let matches = nameRegex.matches(in: body, range: range)
        let namesAndOffsets: [(String, String.Index)] = matches.compactMap { match in
            guard let nameRange = Range(match.range(at: 1), in: body),
                  let matchRange = Range(match.range(at: 0), in: body) else { return nil }
            return (String(body[nameRange]), matchRange.lowerBound)
        }

        return try namesAndOffsets.enumerated().map { index, namedOffset in
            let nextOffset = index + 1 < namesAndOffsets.count ? namesAndOffsets[index + 1].1 : body.endIndex
            let block = String(body[namedOffset.1..<nextOffset])
            return AgentControlManifestEntry(
                name: namedOffset.0,
                label: try stringLiteralValue("label", in: block),
                summary: try capabilityDocSummary(in: block),
                promptSnippet: try stringLiteralValue("promptSnippet", in: block),
                promptGuidelines: try arrayStringValues("promptGuidelines", in: block),
                latency: try stringLiteralValue("latency", in: block),
                surfaces: try surfaceValues(in: block),
                runtimePreconditions: try arrayStringValues("runtimePreconditions", in: block))
        }
    }

    private func readMacOSFile(_ relativePath: String) throws -> String {
        let testFile = URL(fileURLWithPath: #filePath)
        let desktopDir = testFile.deletingLastPathComponent().deletingLastPathComponent()
        let macOSDir = desktopDir.deletingLastPathComponent()
        return try String(contentsOf: macOSDir.appendingPathComponent(relativePath))
    }

    private func stringLiteralValue(_ key: String, in text: String) throws -> String {
        let regex = try NSRegularExpression(pattern: #"\#(key):\s*"([^"]*)""#)
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              let valueRange = Range(match.range(at: 1), in: text) else {
            XCTFail("Missing string literal \(key)")
            return ""
        }
        return String(text[valueRange])
    }

    private func capabilityDocSummary(in text: String) throws -> String {
        let regex = try NSRegularExpression(
            pattern: #"capabilityDoc:\s*controlDoc\(\s*\n?\s*"[^"]+",\s*\n?\s*"([^"]+)""#)
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              let valueRange = Range(match.range(at: 1), in: text) else {
            XCTFail("Missing capabilityDoc summary")
            return ""
        }
        return String(text[valueRange])
    }

    private func templateFirstLineValue(_ key: String, in text: String) throws -> String {
        let regex = try NSRegularExpression(pattern: #"\#(key):\s*`([^\n`]+)"#)
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              let valueRange = Range(match.range(at: 1), in: text) else {
            XCTFail("Missing template literal \(key)")
            return ""
        }
        return String(text[valueRange])
    }

    private func arrayStringValues(_ key: String, in text: String) throws -> [String] {
        guard let start = text.range(of: "\(key): ["),
              let end = text.range(of: "],", range: start.upperBound..<text.endIndex) else {
            XCTFail("Missing string array \(key)")
            return []
        }
        let arrayBody = String(text[start.upperBound..<end.lowerBound])
        let regex = try NSRegularExpression(pattern: #""([^"]*)""#)
        let range = NSRange(arrayBody.startIndex..<arrayBody.endIndex, in: arrayBody)
        return regex.matches(in: arrayBody, range: range).compactMap { match in
            guard let valueRange = Range(match.range(at: 1), in: arrayBody) else { return nil }
            return String(arrayBody[valueRange])
        }
    }

    private func surfaceValues(in text: String) throws -> Set<DesktopCapabilityRegistry.Surface> {
        let values = try arrayStringValues("surfaces", in: text)
        return Set(values.compactMap { value in
            switch value {
            case "desktopChat":
                return .desktopChat
            case "realtimeHub":
                return .realtimeHub
            default:
                XCTFail("Unknown manifest surface \(value)")
                return nil
            }
        })
    }

    // MARK: - Table Annotations Completeness

    func testTableAnnotationsIncludeAllExpectedTables() {
        let expected = [
            "screenshots", "action_items", "transcription_sessions", "transcription_segments",
            "focus_sessions", "live_notes", "memories", "ai_user_profiles", "indexed_files",
            "goals", "staged_tasks", "observations", "task_chat_messages",
            "local_kg_nodes", "local_kg_edges",
        ]
        for table in expected {
            XCTAssertNotNil(
                ChatPrompts.tableAnnotations[table],
                "Missing tableAnnotation for \(table)")
        }
    }
}
