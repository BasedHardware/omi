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

    func testToolPromptHas7Tools() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("You have 7 tools"))
    }

    func testToolPromptListsSearchTasksInWhenToUse() {
        let prompt = ChatPrompts.desktopChat
        XCTAssertTrue(prompt.contains("find tasks about shopping"))
    }

    // MARK: - Onboarding Prompt Suggestion Capability Contract
    //
    // The starter-prompt vocabulary in OnboardingPromptSuggestionBuilder
    // must stay answerable using piMono's 7 tools. These tests lock the
    // invariant so a future edit can't silently overpromise.

    @MainActor
    func testOnboardingPromptsContainNoUnsupportedCapabilities() {
        // Lowercased substrings that signal file/code/shell access — none
        // of which the default piMono chat can do. Intentionally narrow:
        // false positives drown the signal.
        let blockedKeywords = [
            "code",
            "file",
            "bash",
            "shell",
            "terminal",
            "github",
        ]
        for suggestion in OnboardingPromptSuggestionBuilder.allKnownSuggestions {
            let lowered = suggestion.lowercased()
            for keyword in blockedKeywords {
                XCTAssertFalse(
                    lowered.contains(keyword),
                    """
                    Suggestion '\(suggestion)' references blocked capability '\(keyword)'.
                    piMono (default chat mode) cannot read files, run shell commands, or \
                    inspect code. If this suggestion really needs that, it belongs in a \
                    userClaude-mode-conditional set, not in the always-on vocabulary.
                    """
                )
            }
        }
    }

    @MainActor
    func testOnboardingPromptsUniversalIsFirstInVocabulary() {
        XCTAssertEqual(
            OnboardingPromptSuggestionBuilder.allKnownSuggestions.first,
            OnboardingPromptSuggestionBuilder.universalSuggestion,
            "universalSuggestion must always be the first entry — build() prepends it unconditionally"
        )
    }

    @MainActor
    func testOnboardingPromptsVocabularyIsExactlySix() {
        // Upper bound: build() truncates with .prefix(6), so a 7th entry
        // would be unreachable in some onboarding paths. Lower bound:
        // build() emits the universal opener plus up to five named
        // suggestions, all of which must be present in the scanned
        // vocabulary. Pinning to exactly six encodes both constraints.
        XCTAssertEqual(
            OnboardingPromptSuggestionBuilder.allKnownSuggestions.count,
            6,
            "vocabulary must hold exactly the six named suggestions build() can emit"
        )
    }

    @MainActor
    func testOnboardingPromptsVocabularyMatchesNamedSuggestions() {
        // The scanned vocabulary must be exactly the named constants
        // build() draws from — otherwise a suggestion could ship without
        // being capability-scanned, or a scanned string could be dead.
        XCTAssertEqual(
            OnboardingPromptSuggestionBuilder.allKnownSuggestions,
            [
                OnboardingPromptSuggestionBuilder.universalSuggestion,
                OnboardingPromptSuggestionBuilder.emailSuggestion,
                OnboardingPromptSuggestionBuilder.calendarSuggestion,
                OnboardingPromptSuggestionBuilder.goalSuggestion,
                OnboardingPromptSuggestionBuilder.screenSuggestion,
                OnboardingPromptSuggestionBuilder.leverageSuggestion,
            ],
            "allKnownSuggestions must list exactly the named suggestions build() can emit, in order"
        )
    }

    @MainActor
    func testOnboardingPromptVocabularyHasNoDuplicates() {
        let unique = Set(OnboardingPromptSuggestionBuilder.allKnownSuggestions)
        XCTAssertEqual(
            unique.count,
            OnboardingPromptSuggestionBuilder.allKnownSuggestions.count,
            "duplicates in the vocabulary get silently collapsed by build()'s NSOrderedSet dedup — keeps real bugs hidden"
        )
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
