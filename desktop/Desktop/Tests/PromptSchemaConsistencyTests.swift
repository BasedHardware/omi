import XCTest

@testable import Omi_Computer

/// Structural validation that the prompts in `ChatPrompts` stay in
/// lockstep with the runtime they execute against.
///
/// Two specific failure modes these tests guard:
///
///  1. **Tool drift** — A new tool added to the `<tools>` block in the
///     chat prompt but not registered in `ChatToolExecutor.execute(_:)`
///     would make the model emit calls the executor rejects with
///     "Unknown tool", which the user reads as "the AI is dumb".
///
///  2. **Schema drift** — A table or column name in a hardcoded SQL
///     snippet that no longer matches `tableAnnotations` /
///     `columnAnnotations` would silently produce SQL errors. Same
///     user-visible failure mode.
///
/// These validate against the annotation dictionaries in `ChatPrompts`
/// rather than a live `omi.db`: those dictionaries are themselves the
/// schema's source of truth for the prompt (they're what gets
/// serialised into the `{database_schema}` substitution), so checking
/// against them gives the same guarantee with no test fixtures.
///
/// **Scope of validation:** these tests look ONLY at the formal
/// declarations in the prompt — the `<tools>...</tools>` block for
/// tool markers and the `**Common SQL patterns:**` section for SQL
/// snippets. Prose narrative elsewhere in the prompt can mention tool
/// names freely; constraining that is a separate prompt-quality concern.
final class PromptSchemaConsistencyTests: XCTestCase {

    // MARK: - Tool name registry
    //
    // The prompt that formally declares the 7 piMono chat tools is
    // `ChatPrompts.desktopChat` (not `agenticQA`, which is the
    // narrative QA prompt with `<tool_instructions>` but no formal
    // tool block). `desktopChat` is what runtime substitution
    // assembles via `buildSystemPrompt` and what the model actually
    // reads. These tests target `desktopChat` accordingly.

    /// Every `**tool_name**:` marker in the `<tools>` block of
    /// `desktopChat` must correspond to a real tool the executor
    /// dispatches. Scoped to the formal block — narrative tool
    /// mentions elsewhere in the prompt are out of scope (see class
    /// docstring).
    func testDesktopChatToolNamesAreAllRegistered() {
        guard let toolsBlock = Self.extractToolsBlock(from: ChatPrompts.desktopChat) else {
            XCTFail("desktopChat missing <tools>…</tools> markers")
            return
        }
        let toolNames = Self.extractToolNames(from: toolsBlock)
        XCTAssertFalse(
            toolNames.isEmpty,
            "couldn't find any tool markers in desktopChat's <tools> block — regex broken?"
        )
        for name in toolNames {
            XCTAssertTrue(
                ChatToolExecutor.allRegisteredToolNames.contains(name),
                "desktopChat <tools> block declares '\(name)' but ChatToolExecutor.execute(_:) doesn't dispatch it. Add a case or remove the declaration."
            )
        }
    }

    /// Inverse direction: the prompt's tool count claim ("You have 7
    /// tools") must match `piMonoChatToolNames` count. Catches a tool
    /// being added to the executor + prompt body but the count line
    /// going stale.
    func testDesktopChatToolCountClaimMatchesPiMonoRegistry() {
        XCTAssertTrue(
            ChatPrompts.desktopChat.contains(
                "You have \(ChatToolExecutor.piMonoChatToolNames.count) tools"
            ),
            "desktopChat's tool count claim doesn't match the size of piMonoChatToolNames (\(ChatToolExecutor.piMonoChatToolNames.count)). Update both together."
        )
    }

    /// Every tool in `piMonoChatToolNames` must actually appear as a
    /// `**name**:` marker in the prompt. Catches a tool being added
    /// to the executor + registry but missing from the prompt body.
    func testEveryPiMonoToolHasAMarkerInDesktopChat() {
        guard let toolsBlock = Self.extractToolsBlock(from: ChatPrompts.desktopChat) else {
            XCTFail("desktopChat missing <tools>…</tools> markers")
            return
        }
        let toolNames = Self.extractToolNames(from: toolsBlock)
        for expected in ChatToolExecutor.piMonoChatToolNames {
            XCTAssertTrue(
                toolNames.contains(expected),
                "piMonoChatToolNames lists '\(expected)' but desktopChat's <tools> block doesn't declare it. Add a **\(expected)**: section."
            )
        }
    }

    // MARK: - Schema references

    /// Every `FROM <table>`, `JOIN <table>`, `INSERT INTO <table>`,
    /// and `UPDATE <table>` reference in desktopChat's **Common SQL
    /// patterns:** section must point at a table the schema
    /// acknowledges. Scoped to the formal SQL examples block — prose
    /// narrative ("FROM the database", "INSERT INTO multiple rows")
    /// elsewhere in the prompt would otherwise trigger false matches.
    func testDesktopChatSQLReferencesKnownTables() {
        guard let sqlSection = Self.extractCommonSQLPatternsSection(
            from: ChatPrompts.desktopChat
        ) else {
            XCTFail("desktopChat missing the **Common SQL patterns:** section header")
            return
        }
        let tables = Self.extractTableReferences(from: sqlSection)
        XCTAssertFalse(
            tables.isEmpty,
            "no SQL table references found in **Common SQL patterns:** — regex broken or section empty?"
        )
        let known = Set(ChatPrompts.tableAnnotations.keys)
            .union(Self.ftsAndAuxTables)
        for table in tables {
            XCTAssertTrue(
                known.contains(table),
                "desktopChat SQL references table '\(table)' that's not in tableAnnotations or the FTS aux set. Schema drift or typo."
            )
        }
    }

    /// Every column annotation must reference a table that itself
    /// exists in `tableAnnotations`. Catches a stale column-set
    /// hanging on after its table was dropped.
    func testColumnAnnotationTablesAllExistInTableAnnotations() {
        for table in ChatPrompts.columnAnnotations.keys {
            XCTAssertNotNil(
                ChatPrompts.tableAnnotations[table],
                "columnAnnotations has '\(table)' but tableAnnotations doesn't. Orphan annotation."
            )
        }
    }

    // MARK: - Section extraction

    /// Return the substring between `<tools>` and `</tools>`, or nil
    /// if the prompt doesn't declare a formal block.
    private static func extractToolsBlock(from prompt: String) -> String? {
        guard let openRange = prompt.range(of: "<tools>") else { return nil }
        let afterOpen = openRange.upperBound
        guard let closeRange = prompt.range(of: "</tools>", range: afterOpen..<prompt.endIndex)
        else {
            // Open tag present but no close — treat as malformed.
            return nil
        }
        return String(prompt[afterOpen..<closeRange.lowerBound])
    }

    /// Return the substring of the **Common SQL patterns:** section.
    /// The section runs from the marker to the next `**...**` header
    /// (`**Timezone handling:**` etc.).
    private static func extractCommonSQLPatternsSection(from prompt: String) -> String? {
        guard let startRange = prompt.range(of: "**Common SQL patterns:**") else {
            return nil
        }
        let after = startRange.upperBound
        // Find the next `**Header:**` style marker that closes the section.
        let tail = prompt[after...]
        if let nextHeader = tail.range(
            of: #"\*\*[A-Z][^\*]+:\*\*"#,
            options: .regularExpression
        ) {
            return String(prompt[after..<nextHeader.lowerBound])
        }
        // No more headers — section runs to end of prompt.
        return String(tail)
    }

    // MARK: - Extraction helpers

    /// FTS5 virtual tables + other aux tables that aren't user-facing
    /// but legitimately appear in SQL examples. Keep this list short
    /// — anything genuinely new belongs in `tableAnnotations`.
    private static let ftsAndAuxTables: Set<String> = [
        "screenshots_fts",
        "action_items_fts",
        "staged_tasks_fts",
        "task_chat_messages_fts",
        "proactive_extractions_fts",
    ]

    /// Pull `**name**:` markers out of a prompt. The marker convention
    /// is lowercase + underscores ending with a colon, plus digits and
    /// hyphens for forward compat (MCP tool names like
    /// `mcp__omi-tools__execute_sql` carry hyphens; future tool names
    /// could legitimately include digits). Headers like
    /// `**CRITICAL — When to use tools proactively:**` are excluded
    /// because they contain whitespace and uppercase.
    ///
    /// The character class is deliberately `[a-z0-9_\-]+` rather than
    /// `[a-z_]+`: a narrower pattern would silently skip a future tool
    /// whose name contained hyphens or digits, masking the very contract
    /// drift the test exists to catch.
    private static func extractToolNames(from prompt: String) -> Set<String> {
        var names: Set<String> = []
        let pattern = #"\*\*([a-z0-9_\-]+)\*\*:"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(prompt.startIndex..<prompt.endIndex, in: prompt)
        regex.enumerateMatches(in: prompt, range: range) { match, _, _ in
            guard let match = match,
                  match.numberOfRanges > 1,
                  let nameRange = Range(match.range(at: 1), in: prompt)
            else { return }
            names.insert(String(prompt[nameRange]))
        }
        return names
    }

    /// Pull table names from `FROM`, `JOIN`, `INSERT INTO`, `UPDATE`,
    /// and `DELETE FROM` clauses in SQL snippets. Case-insensitive,
    /// permissive about whitespace. Doesn't try to parse subqueries
    /// or CTEs — best-effort regex over hand-written examples.
    private static func extractTableReferences(from prompt: String) -> Set<String> {
        var tables: Set<String> = []
        let patterns = [
            #"\bFROM\s+([a-z_][a-z0-9_]*)"#,
            #"\bJOIN\s+([a-z_][a-z0-9_]*)"#,
            #"\bINSERT\s+INTO\s+([a-z_][a-z0-9_]*)"#,
            #"\bUPDATE\s+([a-z_][a-z0-9_]*)\s+SET"#,
            #"\bDELETE\s+FROM\s+([a-z_][a-z0-9_]*)"#,
        ]
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(
                pattern: pattern,
                options: [.caseInsensitive]
            ) else { continue }
            let range = NSRange(prompt.startIndex..<prompt.endIndex, in: prompt)
            regex.enumerateMatches(in: prompt, range: range) { match, _, _ in
                guard let match = match,
                      match.numberOfRanges > 1,
                      let nameRange = Range(match.range(at: 1), in: prompt)
                else { return }
                tables.insert(String(prompt[nameRange]).lowercased())
            }
        }
        return tables
    }
}
