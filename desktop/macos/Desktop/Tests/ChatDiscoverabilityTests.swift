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

    func testDesktopPromptMentionsTaskAgentStatus() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("**get_task_agent_status**"))
        XCTAssertTrue(prompt.contains("your subagents"))
        XCTAssertTrue(prompt.contains("Call get_task_agent_status"))
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
        let declaredTools = try readToolNames(from: "pi-mono-extension/index.ts")
            .union(readToolNames(from: "agent/src/omi-tools-stdio.ts"))

        for toolName in DesktopCapabilityRegistry.desktopToolNames {
            XCTAssertTrue(declaredTools.contains(toolName), "Missing agent tool declaration for \(toolName)")
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
