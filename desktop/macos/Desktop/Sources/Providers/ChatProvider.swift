import SwiftUI
import Combine
import GRDB
import UniformTypeIdentifiers

// MARK: - UserDefaults Extension for KVO

extension UserDefaults {
    @objc dynamic var multiChatEnabled: Bool {
        return bool(forKey: "multiChatEnabled")
    }
    @objc dynamic var playwrightUseExtension: Bool {
        return bool(forKey: "playwrightUseExtension")
    }
}

// MARK: - Chat Session Model

/// A chat session that groups related messages
struct ChatSession: Identifiable, Codable, Equatable {
    let id: String
    var title: String
    var preview: String?
    let createdAt: Date
    var updatedAt: Date
    let appId: String?
    var messageCount: Int
    var starred: Bool

    enum CodingKeys: String, CodingKey {
        case id, title, preview, starred
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case appId = "app_id"
        case messageCount = "message_count"
    }

    init(id: String = UUID().uuidString, title: String = "New Chat", preview: String? = nil,
         createdAt: Date = Date(), updatedAt: Date = Date(), appId: String? = nil,
         messageCount: Int = 0, starred: Bool = false) {
        self.id = id
        self.title = title
        self.preview = preview
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.appId = appId
        self.messageCount = messageCount
        self.starred = starred
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decodeIfPresent(String.self, forKey: .title) ?? "New Chat"
        preview = try container.decodeIfPresent(String.self, forKey: .preview)
        createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
        appId = try container.decodeIfPresent(String.self, forKey: .appId)
        messageCount = try container.decodeIfPresent(Int.self, forKey: .messageCount) ?? 0
        starred = try container.decodeIfPresent(Bool.self, forKey: .starred) ?? false
    }
}

// MARK: - Content Block Model

/// Structured tool input for inline display
struct ToolCallInput {
    /// Short summary for inline display (e.g., file path, command)
    let summary: String
    /// Full JSON details for expanded view
    let details: String?
}

/// A block of content within an AI message (text or tool call indicator)
enum ChatContentBlock: Identifiable {
    case text(id: String, text: String)
    case toolCall(id: String, name: String, status: ToolCallStatus,
                  toolUseId: String? = nil,
                  input: ToolCallInput? = nil,
                  output: String? = nil)
    case thinking(id: String, text: String)
    /// Collapsible card showing a summary with expandable full text (used for AI profile/discovery)
    case discoveryCard(id: String, title: String, summary: String, fullText: String)

    var id: String {
        switch self {
        case .text(let id, _): return id
        case .toolCall(let id, _, _, _, _, _): return id
        case .thinking(let id, _): return id
        case .discoveryCard(let id, _, _, _): return id
        }
    }

    /// Human-friendly display name for a tool
    static func displayName(for toolName: String) -> String {
        // Strip MCP prefix (e.g., "mcp__omi-tools__execute_sql" → "execute_sql")
        let cleanName: String
        if toolName.hasPrefix("mcp__") {
            cleanName = String(toolName.split(separator: "__").last ?? Substring(toolName))
        } else {
            cleanName = toolName
        }

        // Handle tool names with embedded details (e.g. "WebSearch: \"query\"")
        if cleanName.hasPrefix("WebSearch:") {
            let query = String(cleanName.dropFirst("WebSearch: ".count))
                .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            return query.isEmpty ? "Searching the web" : "Searching: \(query)"
        }
        if cleanName.hasPrefix("WebFetch:") {
            return "Fetching page"
        }
        if cleanName.lowercased().hasPrefix("read:") {
            return "Reading file"
        }
        if cleanName.lowercased().hasPrefix("write:") {
            return "Writing file"
        }
        if cleanName.lowercased().hasPrefix("edit:") {
            return "Editing file"
        }
        if cleanName.lowercased().hasPrefix("bash:") {
            return "Running command"
        }

        switch cleanName {
        case "execute_sql": return "Querying database"
        case "semantic_search": return "Searching conversations"
        case "spawn_agent": return "Starting agent"
        case "run_agent_and_wait": return "Running agent"
        case "search_tasks": return "Searching tasks"
        case "Read": return "Reading file"
        case "Write": return "Writing file"
        case "Edit": return "Editing file"
        case "Bash": return "Running command"
        case "Grep": return "Searching code"
        case "Glob": return "Finding files"
        case "WebSearch": return "Searching the web"
        case "WebFetch": return "Fetching page"
        default: return "Using \(cleanName)"
        }
    }

    /// Tools whose runs are legitimately long — shell commands, file
    /// generation/edits, web fetches, database queries, and delegated
    /// agents. The stall banner ("This is taking longer than usual") is
    /// suppressed for these so normal long work doesn't read as stuck.
    static func isSlowExpectedTool(_ toolName: String) -> Bool {
        let cleaned: String
        if toolName.hasPrefix("mcp__") {
            cleaned = String(toolName.split(separator: "__").last ?? Substring(toolName))
        } else {
            cleaned = toolName
        }
        // Any MCP tool is an out-of-process call we don't time-bound.
        if toolName.hasPrefix("mcp__") { return true }
        let lower = cleaned.lowercased()
        let slowPrefixes = ["bash", "write", "edit", "multiedit", "webfetch", "websearch", "task", "notebookedit"]
        if slowPrefixes.contains(where: { lower.hasPrefix($0) }) { return true }
        let slowExact: Set<String> = [
            "execute_sql", "semantic_search", "spawn_agent",
            "search_tasks", "run_attempt", "run_agent_and_wait", "send_agent_message",
        ]
        // Strip any embedded summary suffix ("Bash: cmd" style) before matching.
        let head = lower.split(separator: ":").first.map(String.init) ?? lower
        return slowExact.contains(head.trimmingCharacters(in: .whitespaces))
    }

    /// Extracts a short summary from tool input for inline display
    static func toolInputSummary(for toolName: String, input: [String: Any]) -> ToolCallInput? {
        let cleanName: String
        if toolName.hasPrefix("mcp__") {
            cleanName = String(toolName.split(separator: "__").last ?? Substring(toolName))
        } else {
            cleanName = toolName
        }

        let summary: String?
        switch cleanName {
        case "Read":
            summary = input["file_path"] as? String
        case "Write", "Edit":
            summary = input["file_path"] as? String
        case "Bash":
            if let cmd = input["command"] as? String {
                summary = cmd.count > 80 ? String(cmd.prefix(80)) + "…" : cmd
            } else {
                summary = nil
            }
        case "Grep":
            let pattern = input["pattern"] as? String ?? ""
            let path = input["path"] as? String
            summary = path != nil ? "\(pattern) in \(path!)" : pattern
        case "Glob":
            summary = input["pattern"] as? String
        case "WebSearch":
            summary = input["query"] as? String
        case "WebFetch":
            summary = input["url"] as? String
        case "execute_sql":
            if let query = input["query"] as? String {
                summary = query.count > 100 ? String(query.prefix(100)) + "…" : query
            } else {
                summary = nil
            }
        case "semantic_search":
            summary = input["query"] as? String
        case "spawn_agent":
            summary = (input["objective"] ?? input["brief"] ?? input["query"]) as? String
        case "run_agent_and_wait":
            summary = input["objective"] as? String
        case "search_tasks":
            summary = input["query"] as? String
        case "request_permission":
            summary = input["type"] as? String
        case "ask_followup":
            summary = input["question"] as? String
        default:
            // Try common key names
            summary = (input["file_path"] ?? input["path"] ?? input["query"] ?? input["command"]) as? String
        }

        guard let summary = summary, !summary.isEmpty else { return nil }

        // Build full details JSON
        let details: String?
        if let data = try? JSONSerialization.data(withJSONObject: input, options: [.prettyPrinted, .sortedKeys]),
           let str = String(data: data, encoding: .utf8) {
            details = str
        } else {
            details = nil
        }

        return ToolCallInput(summary: summary, details: details)
    }
}

enum ToolCallStatus: CaseIterable {
    case running
    /// Promoted by `StallDetector` after the per-tool / inter-event
    /// timer crosses `StallThresholds.slowGapMs`. Still in flight.
    case slow
    /// Promoted after `StallThresholds.stalledGapMs`. Still in flight,
    /// but eligible for the message-level Cancel banner.
    case stalled
    case completed
    /// Terminal failure (timeout, interrupt, bridge error).
    case failed

    /// True for any state where the tool is still working. Pattern
    /// matches throughout the UI should use this instead of `== .running`
    /// so `.slow` and `.stalled` don't accidentally look complete.
    var isInFlight: Bool {
        switch self {
        case .running, .slow, .stalled:
            return true
        case .completed, .failed:
            return false
        }
    }
}

/// Canonical mutation rules for visible tool-call blocks.
/// Adapter streams may emit multiple lifecycle events for one invocation;
/// the chat transcript keeps exactly one block per `toolUseId`.
enum ToolCallBlockUpdater {
    static func applyToolActivity(
        to blocks: inout [ChatContentBlock],
        toolName: String,
        status: ToolCallStatus,
        toolUseId: String?,
        input: [String: Any]?
    ) {
        let normalizedToolUseId = toolUseId?.isEmpty == false ? toolUseId : nil
        let toolInput = input.flatMap { ChatContentBlock.toolInputSummary(for: toolName, input: $0) }

        if status == .running {
            if let existingIndex = existingToolIndexForStart(
                in: blocks,
                toolName: toolName,
                toolUseId: normalizedToolUseId
            ) {
                if case .toolCall(let id, let name, let existingStatus, let existingToolUseId, let existingInput, let output) =
                    blocks[existingIndex] {
                    blocks[existingIndex] = .toolCall(
                        id: id,
                        name: name,
                        status: existingStatus,
                        toolUseId: normalizedToolUseId ?? existingToolUseId,
                        input: toolInput ?? existingInput,
                        output: output
                    )
                }
                return
            }

            blocks.append(
                .toolCall(
                    id: UUID().uuidString,
                    name: toolName,
                    status: .running,
                    toolUseId: normalizedToolUseId,
                    input: toolInput
                )
            )
            return
        }

        for index in blocks.indices {
            guard case .toolCall(let id, let name, let existingStatus, let existingToolUseId, let existingInput, let output) =
                blocks[index],
                  existingStatus.isInFlight,
                  toolMatches(
                    name: name,
                    toolUseId: existingToolUseId,
                    requestedName: toolName,
                    requestedToolUseId: normalizedToolUseId
                  ) else {
                continue
            }

            blocks[index] = .toolCall(
                id: id,
                name: name,
                status: status,
                toolUseId: normalizedToolUseId ?? existingToolUseId,
                input: toolInput ?? existingInput,
                output: output
            )
        }
    }

    static func completeRemainingToolCalls(
        in blocks: inout [ChatContentBlock],
        terminalStatus: ToolCallStatus = .completed
    ) {
        for index in blocks.indices {
            if case .toolCall(let id, let name, let status, let toolUseId, let input, let output) = blocks[index],
               status.isInFlight {
                blocks[index] = .toolCall(
                    id: id,
                    name: name,
                    status: terminalStatus,
                    toolUseId: toolUseId,
                    input: input,
                    output: output
                )
            }
        }
    }

    static func applyToolOutput(
        to blocks: inout [ChatContentBlock],
        toolUseId: String,
        name: String,
        output: String
    ) {
        let normalizedToolUseId = toolUseId.isEmpty ? nil : toolUseId
        for index in blocks.indices {
            guard case .toolCall(let id, let blockName, let status, let existingToolUseId, let input, _) =
                blocks[index],
                  toolMatches(
                    name: blockName,
                    toolUseId: existingToolUseId,
                    requestedName: name,
                    requestedToolUseId: normalizedToolUseId
                  ) else {
                continue
            }

            blocks[index] = .toolCall(
                id: id,
                name: blockName,
                status: status,
                toolUseId: normalizedToolUseId ?? existingToolUseId,
                input: input,
                output: output
            )
        }
    }

    private static func existingToolIndexForStart(
        in blocks: [ChatContentBlock],
        toolName: String,
        toolUseId: String?
    ) -> Int? {
        if let toolUseId {
            for index in stride(from: blocks.count - 1, through: 0, by: -1) {
                guard case .toolCall(_, _, _, let existingToolUseId, _, _) = blocks[index] else {
                    continue
                }
                if existingToolUseId == toolUseId {
                    return index
                }
            }
        }

        for index in stride(from: blocks.count - 1, through: 0, by: -1) {
            guard case .toolCall(_, let name, let status, let existingToolUseId, _, _) = blocks[index],
                  status.isInFlight else {
                continue
            }

            if existingToolUseId == nil && name == toolName {
                return index
            }
        }
        return nil
    }

    private static func toolMatches(
        name: String,
        toolUseId: String?,
        requestedName: String,
        requestedToolUseId: String?
    ) -> Bool {
        if let requestedToolUseId {
            return toolUseId == requestedToolUseId || (toolUseId == nil && name == requestedName)
        }
        return name == requestedName
    }
}

final class ChatResponseMetrics: @unchecked Sendable {
    struct Snapshot {
        let sqlRowsReturned: Int
        let sqlQueryCount: Int
    }

    private let lock = NSLock()
    private var isFirstResponse = true
    private var isGenerating = false
    private var sqlRowsReturned = 0
    private var sqlQueryCount = 0

    func markFirstOutputIfNeeded() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard isFirstResponse else { return false }
        isFirstResponse = false
        return true
    }

    func markGenerationStartedIfNeeded() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard !isGenerating else { return false }
        isGenerating = true
        return true
    }

    func recordToolResult(name: String, result: String) {
        guard name == "execute_sql" else { return }
        let rowsReturned = Self.sqlRowsReturned(in: result)
        lock.lock()
        sqlQueryCount += 1
        sqlRowsReturned += rowsReturned
        lock.unlock()
    }

    func snapshot() -> Snapshot {
        lock.lock()
        defer { lock.unlock() }
        return Snapshot(sqlRowsReturned: sqlRowsReturned, sqlQueryCount: sqlQueryCount)
    }

    private static func sqlRowsReturned(in result: String) -> Int {
        guard let match = result.range(of: #"(\d+) row\(s\)"#, options: .regularExpression) else {
            return 0
        }
        let numStr = result[match].components(separatedBy: " ").first ?? "0"
        return Int(numStr) ?? 0
    }
}

// MARK: - Chat Message Model

/// Metadata about the context and resources used to generate an AI response
struct MessageMetadata {
    var model: String?
    var inputTokens: Int?
    var outputTokens: Int?
    var cacheReadTokens: Int?
    var cacheWriteTokens: Int?
    var costUsd: Double?
    var systemPrompt: String?
    var hasScreenshot: Bool
    var screenshotSizeBytes: Int?
    var toolNames: [String]
    /// Total rows returned across all execute_sql tool calls during this response
    var sqlRowsReturned: Int
    /// Number of execute_sql tool calls made during this response
    var sqlQueryCount: Int

    var totalTokens: Int? {
        guard let input = inputTokens, let output = outputTokens else { return nil }
        return input + output + (cacheReadTokens ?? 0) + (cacheWriteTokens ?? 0)
    }

    // MARK: - Dynamic context sections from system prompt

    /// A single tagged section found in the system prompt
    struct PromptSection {
        let tag: String
        let itemCount: Int
        let charCount: Int

        /// Human-readable label derived from the XML tag name
        var label: String {
            tag.replacingOccurrences(of: "_", with: " ")
                .localizedCapitalized
        }
    }

    /// Dynamically discovers all XML-tagged sections in the system prompt and counts items in each.
    /// This is future-proof: any new `<some_tag>...</some_tag>` section automatically appears.
    var promptSections: [PromptSection] {
        guard let prompt = systemPrompt else { return [] }
        var sections: [PromptSection] = []
        var seen = Set<String>()

        // Find all <tag>...</tag> pairs
        let pattern = try! NSRegularExpression(pattern: #"<([a-z][a-z0-9_]*)>"#, options: [])
        let matches = pattern.matches(in: prompt, range: NSRange(prompt.startIndex..., in: prompt))

        for match in matches {
            guard let tagRange = Range(match.range(at: 1), in: prompt) else { continue }
            let tag = String(prompt[tagRange])

            // Skip duplicates
            guard !seen.contains(tag) else { continue }
            seen.insert(tag)

            let openTag = "<\(tag)>"
            let closeTag = "</\(tag)>"
            guard let openRange = prompt.range(of: openTag),
                  let closeRange = prompt.range(of: closeTag),
                  openRange.upperBound < closeRange.lowerBound else { continue }

            let content = String(prompt[openRange.upperBound..<closeRange.lowerBound])
            let charCount = content.count

            // Count meaningful lines (items starting with "- ", or role-prefixed lines for conversation)
            let lines = content.components(separatedBy: "\n")
            let itemCount: Int
            if tag == "conversation_history" {
                itemCount = lines.filter { $0.hasPrefix("User:") || $0.hasPrefix("Assistant:") }.count
            } else {
                let bulletLines = lines.filter { $0.trimmingCharacters(in: .whitespaces).hasPrefix("- ") }.count
                // If no bullet items, count non-empty non-header lines
                if bulletLines > 0 {
                    itemCount = bulletLines
                } else {
                    itemCount = lines.filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.count
                }
            }

            sections.append(PromptSection(tag: tag, itemCount: itemCount, charCount: charCount))
        }

        return sections
    }

    // Backward-compatible summary counts used by the floating-bar metadata popover.
    // These intentionally keep the older semantics instead of exposing every raw XML section.
    var memoriesCount: Int {
        guard let prompt = systemPrompt,
              let factsStart = prompt.range(of: "<user_facts>"),
              let factsEnd = prompt.range(of: "</user_facts>") else { return 0 }
        let factsSection = String(prompt[factsStart.upperBound..<factsEnd.lowerBound])
        return factsSection
            .components(separatedBy: "\n")
            .filter { $0.trimmingCharacters(in: .whitespaces).hasPrefix("- ") }
            .count
    }

    var conversationTurns: Int {
        guard let prompt = systemPrompt,
              let histStart = prompt.range(of: "<conversation_history>"),
              let histEnd = prompt.range(of: "</conversation_history>") else { return 0 }
        let histSection = String(prompt[histStart.upperBound..<histEnd.lowerBound])
        return histSection
            .components(separatedBy: "\n")
            .filter { $0.hasPrefix("User:") || $0.hasPrefix("Assistant:") }
            .count
    }

    var tasksCount: Int {
        guard let prompt = systemPrompt,
              let tasksStart = prompt.range(of: "<user_tasks>"),
              let tasksEnd = prompt.range(of: "</user_tasks>") else { return 0 }
        let tasksSection = String(prompt[tasksStart.upperBound..<tasksEnd.lowerBound])
        return tasksSection
            .components(separatedBy: "\n")
            .filter { $0.trimmingCharacters(in: .whitespaces).hasPrefix("- ") }
            .count
    }

    var goalsCount: Int {
        guard let prompt = systemPrompt,
              let goalsStart = prompt.range(of: "<user_goals>"),
              let goalsEnd = prompt.range(of: "</user_goals>") else { return 0 }
        let goalsSection = String(prompt[goalsStart.upperBound..<goalsEnd.lowerBound])
        return goalsSection
            .components(separatedBy: "\n")
            .filter { $0.trimmingCharacters(in: .whitespaces).hasPrefix("- ") }
            .count
    }

    var availableToolsCount: Int {
        guard let prompt = systemPrompt else { return 0 }
        return [
            "execute_sql",
            "semantic_search",
            "spawn_agent",
            "run_agent_and_wait",
            "search_tasks",
            "get_daily_recap",
            "complete_task",
            "delete_task",
            "save_knowledge_graph"
        ]
        .filter { prompt.contains("**\($0)**") }
        .count
    }
}

/// A single chat message
struct ChatMessage: Identifiable {
    var id: String  // Mutable to sync with server-generated ID
    let clientTurnId: String?
    var text: String
    let createdAt: Date
    let sender: ChatSender
    var isStreaming: Bool
    /// Rating: 1 = thumbs up, -1 = thumbs down, nil = no rating
    var rating: Int?
    /// Whether the message has been synced with the backend (has valid server ID)
    var isSynced: Bool
    /// Citations extracted from the AI response
    var citations: [Citation]
    /// Structured content blocks for AI messages (text interspersed with tool calls)
    var contentBlocks: [ChatContentBlock]
    /// Metadata about context used to generate this response (AI messages only)
    var metadata: MessageMetadata?
    /// Context text for proactive notification messages (not shown to user, sent to Claude)
    var notificationContext: String?
    /// Screenshot JPEG data captured when a proactive notification was generated
    var notificationScreenshot: Data?
    /// User-attached files (screenshots, images, documents) — populated for user messages.
    var attachments: [ChatAttachment]
    /// Surface-neutral resources associated with this message. Assistant messages
    /// use this for generated artifacts; user messages derive resources from
    /// `attachments` for backwards compatibility.
    var resources: [ChatResource]

    init(id: String = UUID().uuidString, clientTurnId: String? = nil, text: String, createdAt: Date = Date(), sender: ChatSender, isStreaming: Bool = false, rating: Int? = nil, isSynced: Bool = false, citations: [Citation] = [], contentBlocks: [ChatContentBlock] = [], metadata: MessageMetadata? = nil, notificationContext: String? = nil, notificationScreenshot: Data? = nil, attachments: [ChatAttachment] = [], resources: [ChatResource] = []) {
        self.id = id
        self.clientTurnId = clientTurnId
        self.text = text
        self.createdAt = createdAt
        self.sender = sender
        self.isStreaming = isStreaming
        self.rating = rating
        self.isSynced = isSynced
        self.citations = citations
        self.contentBlocks = contentBlocks
        self.metadata = metadata
        self.notificationContext = notificationContext
        self.notificationScreenshot = notificationScreenshot
        self.attachments = attachments
        self.resources = resources
    }
}

extension ChatMessage {
    var copyableText: String {
        let structuredText = contentBlocks
            .compactMap(\.copyableText)
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !structuredText.isEmpty {
            return structuredText
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var displayResources: [ChatResource] {
        if !resources.isEmpty {
            return resources
        }
        return attachments.map(ChatResource.attachment)
    }
}

extension ChatContentBlock {
    var copyableText: String? {
        switch self {
        case .text(_, let text):
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        case .thinking(_, let text):
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : "Thinking:\n\(trimmed)"
        case .discoveryCard(_, let title, _, let fullText):
            let trimmed = fullText.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? title : "\(title)\n\(trimmed)"
        case .toolCall:
            return nil
        }
    }
}

enum ChatSender {
    case user
    case ai
}

enum ChatTurnOwner: Equatable {
    case mainChat
    case floatingDefault
    case floatingVoice
    case taskChat(String)
    case agentPill(UUID)

    func canInterrupt(_ activeOwner: ChatTurnOwner) -> Bool {
        switch (self, activeOwner) {
        case (.floatingDefault, .floatingDefault),
             (.floatingDefault, .floatingVoice),
             (.floatingVoice, .floatingDefault),
             (.floatingVoice, .floatingVoice):
            return true
        case (.taskChat(let lhs), .taskChat(let rhs)):
            return lhs == rhs
        case (.agentPill(let lhs), .agentPill(let rhs)):
            return lhs == rhs
        default:
            return self == activeOwner
        }
    }
}

extension ChatMessage {
    /// Convert a backend message to a local ChatMessage
    init(from db: ChatMessageDB) {
        let resources = ChatResource.decodeResourcesFromMessageMetadata(db.metadata)
        self.init(
            id: db.id,
            text: db.text,
            createdAt: db.createdAt,
            sender: db.sender == "human" ? .user : .ai,
            isStreaming: false,
            rating: db.rating,
            isSynced: true,
            attachments: ChatMessage.decodeAttachments(from: db.metadata),
            resources: resources
        )
    }

    /// Parse the `attachments` array from a message's persisted metadata JSON.
    /// Format (mirrors `MessageMetadata.attachmentsJSON()` on send):
    ///   `{ "attachments": [ { "id": "...", "name": "...", "mime_type": "...", "thumbnail": "..." } ] }`
    static func decodeAttachments(from metadataJSON: String?) -> [ChatAttachment] {
        guard let json = metadataJSON, let data = json.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let raw = root["attachments"] as? [[String: Any]]
        else { return [] }
        return raw.compactMap { item -> ChatAttachment? in
            guard let id = item["id"] as? String else { return nil }
            let name = (item["name"] as? String) ?? "file"
            let mime = (item["mime_type"] as? String) ?? "application/octet-stream"
            let thumb = item["thumbnail"] as? String
            return ChatAttachment(
                id: id,
                fileName: name,
                mimeType: mime,
                data: nil,
                serverId: id,
                thumbnailURL: thumb,
                state: .uploaded
            )
        }
    }
}

// MARK: - Citation Model

/// A citation referencing a source conversation or memory
struct Citation: Identifiable {
    let id: String
    let sourceType: CitationSourceType
    let title: String
    let preview: String
    let emoji: String?
    let createdAt: Date?

    enum CitationSourceType {
        case conversation
        case memory
    }
}

// MARK: - Chat Mode

/// Controls whether the AI agent can perform write actions (Act) or is restricted to read-only (Ask)
enum ChatMode: String, CaseIterable {
    case ask
    case act
}

enum ChatSystemPromptStyle {
    case main
    case floating

    var includesDatabaseSchema: Bool { self == .main }
    var includesSkills: Bool { self == .main }
}

/// State management for chat functionality with Claude Agent SDK
/// Uses hybrid architecture: Swift → Claude Agent (via Node.js bridge) for AI, Backend for persistence + context
@MainActor
class ChatProvider: ObservableObject {

    /// Weak reference to the app-root main-window instance (set by
    /// ViewModelContainer.init()), so the local automation bridge can drive
    /// the real main chat surface in-process — no synthetic mouse/keyboard
    /// input, so it never touches the user's actual cursor.
    static weak var mainInstance: ChatProvider?

    // MARK: - Floating Bar System Prompt Prefix
    /// Static prefix injected at the top of the system prompt for floating bar sessions.
    /// Defined here so it can be referenced both at warmup time and at query time.
    static let floatingBarSystemPromptPrefix = """
================================================================================
🚨 FLOATING BAR MODE — READ THIS FIRST BEFORE ANYTHING ELSE 🚨
================================================================================
SCOPE TOOLS TO THE USER'S OWN DATA. First decide whether the question actually needs the user's personal data. If it's about the user — their memories, facts, preferences, past conversations, tasks, schedule, goals, or app/screen activity — use the available data tools (get_memories, search_memories, execute_sql, get_daily_recap, etc.) to look it up before answering; don't guess. If it's chit-chat, a greeting, or general knowledge that does NOT depend on the user's data, answer directly and immediately WITHOUT calling any tools. The user expects personalized answers when the question is about them — but not a tool round-trip for "hey" or a general question.
NEVER ask follow-up questions or ask for clarification. ALWAYS give a direct, concrete answer immediately using whatever you know about the user from their memories, context, and facts. If memories mention their devices, preferences, work, budget, or interests — use that to give a specific recommendation, not a generic one.
Search the web only when you genuinely need current or unfamiliar information you don't already know (e.g. a product/version detail you're unsure of). Don't reflexively look up things you already know — answer general knowledge directly.
If a screenshot is attached and the user asks a deictic question like "which one", "which option", "which suits me", "what should I choose", or "what's on my screen", ground the answer in the visible options first and prefer what is actually on screen over unrelated context.
If the screenshot already clearly shows the relevant options, do not ignore it just because the query is short or ambiguous.
Respond concisely in 1-2 sentences. No lists. No headers. NEVER ask follow-up questions — just answer.
A screenshot may be attached — use it silently only if relevant. Never mention or acknowledge it.
BROWSER TABS: when you use the browser (Playwright), on your FIRST browser action open ONE dedicated tab with the browser_tabs tool (action: "new"), then do ALL browser work in that single tab and reuse it for every step. NEVER navigate, reload, switch, or close the user's other tabs, and never hijack their active tab — work only in the tab you opened so you don't interfere with what the user is doing.
================================================================================
"""

    // MARK: - Published State
    @Published var chatMode: ChatMode = .act
    @Published var draftText = ""
    /// Files staged for attachment to the next message. Cleared when the message is sent.
    @Published var pendingAttachments: [ChatAttachment] = []
    @Published var messages: [ChatMessage] = []
    @Published var sessions: [ChatSession] = []
    @Published var currentSession: ChatSession?
    @Published var isLoading = false
    @Published var isLoadingSessions = true  // Start true since we load sessions on init
    @Published var isSending = false
    @Published var isStopping = false
    @Published private(set) var activeTurnOwner: ChatTurnOwner?
    @Published var isClearing = false
    @Published var errorMessage: String?
    /// Monotonic token that increments each time the local user sends a message.
    /// ChatMessagesView observes this to anchor the viewport on send, rather than
    /// inferring solely from messages.count changes (which can also come from
    /// polling/sync).
    @Published var localSendToken: LocalSendToken = LocalSendToken(generation: 0)

    // MARK: - ChatErrorState (structured replacement for the inline error banner)
    //
    // Structured error state for the chat surface. Drives the
    // ChatErrorCard view. Coexists with the legacy `errorMessage`
    // banner: mappable BridgeError cases set `currentError` and clear
    // `errorMessage`; unmappable cases (encoding, quota, agent errors
    // with free-form messages) keep falling back to the legacy banner.
    //
    // Paywall sheets (`isClaudeAuthRequired`, `needsBrowserExtensionSetup`,
    // `showOmiThresholdAlert`) are deliberately NOT migrated — they're
    // product flows, not error recovery surfaces.
    @Published var currentError: ChatErrorState?

    /// Captured at the start of each sendMessage so the .retry recovery
    /// action can re-issue the user's last prompt. Cleared after a
    /// successful re-send or on dismiss to avoid stale retries.
    private var lastFailedPrompt: String?
    private var pendingErrorRecoveryPrompt: String?

    /// Monotonically-incremented id for each sendMessage / stopAgent cycle.
    /// Watchdog tasks capture their gen and only reset state if it still
    /// matches — so a watchdog fired by a stuck send #N won't cancel a
    /// later, healthy send #N+1. See sendMessage() and stopAgent().
    private var sendGeneration: Int = 0
    private var activeBridgeSendGeneration: Int?

    /// Set to true during onboarding so the ACP session ID is persisted for restart recovery.
    var isOnboarding = false
    @Published var sessionsLoadError: String?
    @Published var selectedAppId: String?
    @Published var hasMoreMessages = false
    @Published var isLoadingMoreMessages = false
    @Published var showStarredOnly = false
    @Published var searchQuery = ""
    /// Pre-computed grouped sessions for sidebar display.
    /// Updated reactively via Combine instead of recomputed on every SwiftUI render pass.
    @Published private(set) var groupedSessions: [(String, [ChatSession])] = []

    /// Triggered when a browser tool is called but the extension token isn't configured.
    /// The UI should observe this and present BrowserExtensionSetup.
    @Published var needsBrowserExtensionSetup = false

    /// Whether the user is currently viewing the default chat (syncs with Flutter app)
    @Published var isInDefaultChat = true

    /// Working directory for Claude Agent SDK file-system tools (Read, Write, Bash, etc.)
    /// Set by TaskChatCoordinator to point at the user's project directory.
    var workingDirectory: String?

    /// Override app ID for message routing (e.g. "task-chat" to isolate task messages).
    /// When set, messages are saved with this app_id so the backend routes them
    /// to the correct session instead of the default chat.
    var overrideAppId: String?

    /// Override the Claude model for this provider's queries.
    /// When set, the bridge uses this model instead of the default (Opus).
    /// e.g. "claude-sonnet-4-6" for faster floating bar responses.
    var modelOverride: String?
    /// Optional per-provider bridge override for spawned/background agents.
    /// This lets a single pill run Hermes/OpenClaw without changing the user's
    /// global chat provider preference stored in `chatBridgeMode`.
    private let bridgeHarnessOverride: AgentHarnessMode?

    var hasBridgeHarnessOverride: Bool {
        bridgeHarnessOverride != nil
    }

    /// Multi-chat mode setting - when false, only default chat is shown (syncs with Flutter)
    /// When true, user can create multiple chat sessions
    @AppStorage("multiChatEnabled") var multiChatEnabled = false

    // MARK: - Agent client
    // NOTE: initialized lazily so it reads the persisted bridgeMode from UserDefaults,
    // not always defaulting to Omi mode on cold start.
    private var agentClient: AgentClient.Session?
    private func resolvedAgentClient() -> AgentClient.Session {
        if let agentClient { return agentClient }
        let harness = resolvedHarnessMode()
        activeBridgeHarness = harness
        let session = AgentClient.makeSession(harnessMode: harness)
        agentClient = session
        return session
    }
    lazy var kernelTurnProjection = KernelTurnProjection(host: self)
    private var agentBridgeStarted = false
    /// Tracks the harness mode the bridge is actually running (NOT the @AppStorage preference).
    /// @AppStorage("chatBridgeMode") can be updated by other views sharing the same key,
    /// so comparing against it in switchBridgeMode() would always match → no-op.
    private var activeBridgeHarness: String = "piMono"
    /// True while switchBridgeMode is in the critical section between stopping the old
    /// bridge and starting the new one.  sendMessage checks this to avoid racing.
    private var modeSwitchInProgress = false
    /// Continuations for callers waiting on an in-flight mode switch. Supports
    /// arbitrary overlap (A→B→A→B) without losing waiters.
    private var modeSwitchWaiters: [CheckedContinuation<Void, Never>] = []

    enum BridgeMode: String {
        case omiAI = "agentSDK"     // Legacy, auto-migrated to piMono
        case userClaude = "claudeCode"
        case piMono = "piMono"
        case hermes = "hermes"
        case openClaw = "openclaw"
    }
    @AppStorage("chatBridgeMode") var bridgeMode: String = BridgeMode.piMono.rawValue

    var isUsingOmiAccountProvider: Bool {
        resolvedHarnessMode() == "piMono"
    }

    nonisolated static func harnessMode(for mode: BridgeMode) -> String {
        AgentRuntimeRouting.harnessMode(for: mode).rawValue
    }

    private func resolvedHarnessMode() -> String {
        if let override = bridgeHarnessOverride {
            return override.rawValue
        }
        let mode = UserDefaults.standard.string(forKey: "chatBridgeMode") ?? BridgeMode.piMono.rawValue
        return Self.harnessMode(for: BridgeMode(rawValue: mode) ?? .piMono)
    }

    /// The legacy "$50 lifetime Omi AI spend" upgrade nudge (`showOmiThresholdAlert`)
    /// must never fire for users who already pay — paid subscribers and BYOK users
    /// aren't capped by the free Omi quota. `omiAICumulativeCostUsd` is seeded from the
    /// backend *lifetime* total, so without this guard any heavy paying user (e.g. on
    /// Operator/Architect) trips $50 and gets a bogus "Upgrade Required" alert even
    /// while well within their plan. The authoritative free-tier block is the
    /// server-side quota in `FloatingBarUsageLimiter`; this is just a soft nudge.
    var isExemptFromOmiUpgradeNudge: Bool {
        FloatingBarUsageLimiter.shared.hasPaidPlan || APIKeyService.isByokActive
    }

    /// Whether the agent bridge requires authentication (shown as sheet in UI)
    @Published var isClaudeAuthRequired = false
    /// Auth methods returned by agent bridge
    @Published var claudeAuthMethods: [[String: Any]] = []
    /// OAuth URL to open in browser (sent by bridge when auth is needed)
    @Published var claudeAuthUrl: String?
    /// Whether the user has a cached Claude OAuth token
    @Published var isClaudeConnected = false
    /// Cumulative tokens used in the current session via Omi account
    @Published var sessionTokensUsed: Int = 0
    /// Cumulative USD cost spent using the Omi account, persisted across sessions.
    /// Used to enforce the $50 threshold for auto-switching to the user's Claude account.
    @AppStorage("omiAICumulativeCostUsd") var omiAICumulativeCostUsd: Double = 0.0
    /// Set to true when the $50 Omi account usage threshold is reached, triggering an alert.
    @Published var showOmiThresholdAlert = false

    private let messagesPageSize = 50
    /// Raw server records consumed by history pagination (the backend pages newest-first).
    /// Kept separate from messages.count: deduped pages and live messages merged by
    /// polling would otherwise stall or skew the offset.
    private var messagesPaginationOffset = 0

    /// Reset history-pagination state. Must accompany every clear/replace of
    /// `messages` outside the two loaders (`selectSession`,
    /// `loadDefaultChatMessages`), which set both fields from a fresh fetch.
    private func resetMessagesPagination() {
        messagesPaginationOffset = 0
        hasMoreMessages = false
    }

    private var multiChatObserver: AnyCancellable?
    private var playwrightExtensionObserver: AnyCancellable?
    private var sessionGroupingObserver: AnyCancellable?
    private var activationObserver: AnyCancellable?
    private var signOutObserver: AnyCancellable?

    private var refreshAllObserver: AnyCancellable?

    // MARK: - Streaming Buffer
    /// Accumulates text deltas during streaming and flushes them to the published
    /// messages array at most once per ~100ms, reducing SwiftUI re-render frequency.
    private var streamingTextBuffer: String = ""
    private var streamingThinkingBuffer: String = ""
    private var streamingBufferMessageId: String?
    private var streamingFlushWorkItem: DispatchWorkItem?
    private let streamingFlushInterval: TimeInterval = 0.035

    // MARK: - Filtered Sessions
    var filteredSessions: [ChatSession] {
        // Filter out "empty" sessions (only AI greeting, no user messages)
        // These have messageCount <= 1 and default "New Chat" title
        // Always keep the currently selected session visible
        let nonEmptySessions = sessions.filter { session in
            // Always show the current session (so user can continue working)
            if session.id == currentSession?.id { return true }
            // Keep sessions that have user messages (more than just AI greeting)
            // or have been renamed (user intentionally kept them)
            return session.messageCount > 1 || session.title != "New Chat"
        }

        guard !searchQuery.isEmpty else { return nonEmptySessions }
        let query = searchQuery.lowercased()
        return nonEmptySessions.filter { session in
            session.title.lowercased().contains(query) ||
            (session.preview?.lowercased().contains(query) ?? false)
        }
    }

    // MARK: - Cached Context for Prompts
    private var cachedMemories: [ServerMemory] = []
    private var memoriesLoaded = false
    private var cachedGoals: [Goal] = []
    private var goalsLoaded = false
    private var cachedTasks: [TaskActionItem] = []
    private var tasksLoaded = false
    private var cachedAIProfile: String = ""
    private var aiProfileLoaded = false
    private var cachedDatabaseSchema: String = ""
    private var schemaLoaded = false
    /// System prompt built once at warmup and reused for every query.
    /// Turn context (history, coordinator route, context packet) is assembled by the kernel.
    private var cachedMainSystemPrompt: String = ""
    private var cachedFloatingSystemPrompt: String = ""
    private var cachedFloatingPillSystemPrompt: String = ""

    // MARK: - CLAUDE.md & Skills (Global)
    @Published var claudeMdContent: String?
    @Published var claudeMdPath: String?
    @Published var discoveredSkills: [(name: String, description: String, path: String)] = []
    @AppStorage("claudeMdEnabled") var claudeMdEnabled = true
    @AppStorage("disabledSkillsJSON") private var disabledSkillsJSON: String = ""

    // MARK: - Project-level CLAUDE.md & Skills
    @AppStorage("aiChatWorkingDirectory") var aiChatWorkingDirectory: String = ""
    @Published var projectClaudeMdContent: String?
    @Published var projectClaudeMdPath: String?
    @Published var projectDiscoveredSkills: [(name: String, description: String, path: String)] = []
    @AppStorage("projectClaudeMdEnabled") var projectClaudeMdEnabled = true

    // MARK: - Dev Mode
    @AppStorage("devModeEnabled") var devModeEnabled = false
    private var devModeContext: String?

    // MARK: - Current Session ID
    var currentSessionId: String? {
        currentSession?.id
    }

    // MARK: - Current Model
    var currentModel: String {
        "Claude"
    }

    // MARK: - System Prompt
    // Prompts are defined in ChatPrompts.swift (converted from Python backend)

    init(bridgeHarnessOverride: AgentHarnessMode? = nil) {
        self.bridgeHarnessOverride = bridgeHarnessOverride
        log("ChatProvider initialized, will start Claude bridge on first use")

        // When the last in-flight save completes, re-run any poll cycle
        // that was deferred while saves were active. Keeps suppression
        // from permanently dropping a fetch of other-platform messages.
        //
        // The flag is intentionally NOT cleared here — only
        // `pollForNewMessages` clears it, and only once it actually gets
        // past its guards and commits to a fetch. Otherwise a retry that
        // bails again (e.g. on `isSending` because the next turn is mid-
        // stream) would drop the deferral permanently; leaving the flag
        // set lets the next drain (e.g. the AI-response save) retry once
        // sending has finished.
        pendingSaves.onDrained = { [weak self] in
            guard let self, self.pollDeferredDuringSave else { return }
            Task { [weak self] in await self?.pollForNewMessages() }
        }

        // Migrate legacy "agentSDK" persisted mode to the new default "piMono".
        // Pre-6594 installs may have the old agentSDK tag saved; the settings
        // picker no longer offers it, so leaving it stored would leave the UI
        // in an inconsistent state.
        let stored = UserDefaults.standard.string(forKey: "chatBridgeMode")
        if stored == BridgeMode.omiAI.rawValue {
            UserDefaults.standard.set(BridgeMode.piMono.rawValue, forKey: "chatBridgeMode")
            log("ChatProvider: migrated legacy agentSDK bridgeMode -> piMono")
        }

        // Observe changes to multiChatEnabled setting
        multiChatObserver = UserDefaults.standard.publisher(for: \.multiChatEnabled)
            .dropFirst() // Skip initial value
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                Task { @MainActor in
                    await self?.reinitialize()
                }
            }

        // Refresh messages when app becomes active
        activationObserver = NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)
            .sink { [weak self] _ in
                Task { @MainActor in
                    await self?.pollForNewMessages()
                }
            }

        // Tear down the agent bridge on sign-out. The pi-mono subprocess
        // bakes OMI_API_KEY (Firebase ID token) at spawn and holds an
        // in-memory `piSessions` map keyed only by legacy harness scope ("main"). When
        // the user signs out + back in with a different account, the next
        // message would otherwise reuse the previous user's session and the
        // omi-account proxy returns 402 against the old token. Stopping the
        // subprocess drops both the token and the session map; the next
        // sendMessage will spawn a fresh subprocess via ensureBridgeStarted.
        signOutObserver = NotificationCenter.default.publisher(for: .userDidSignOut)
            .sink { [weak self] _ in
                Task { @MainActor in
                    guard let self = self else { return }
                    log("ChatProvider: userDidSignOut — clearing chat state so the next user gets fresh context")
                    if self.agentBridgeStarted {
                        await self.resolvedAgentClient().clearOwnerState()
                        await self.resolvedAgentClient().stop()
                        self.agentBridgeStarted = false
                    }
                    self.resetSessionStateForAuthChange()
                    AgentRuntimeStatusStore.shared.reset()
                }
            }

        // Cmd+R: refresh messages on demand
        refreshAllObserver = NotificationCenter.default.publisher(for: .refreshAllData)
            .sink { [weak self] _ in
                Task { @MainActor in
                    await self?.pollForNewMessages()
                }
            }

        // Observe changes to Playwright extension mode setting — restart bridge to pick up new env vars
        playwrightExtensionObserver = UserDefaults.standard.publisher(for: \.playwrightUseExtension)
            .dropFirst()
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                Task { @MainActor in
                    guard let self = self else { return }
                    guard !self.isSending else {
                        log("ChatProvider: Skipping bridge restart — query in progress")
                        return
                    }
                    guard !self.modeSwitchInProgress else {
                        log("ChatProvider: Playwright setting changed but mode switch in progress — skipping bridge restart")
                        return
                    }
                    guard self.agentBridgeStarted else { return }
                    log("ChatProvider: Playwright extension setting changed, restarting agent bridge")
                    self.agentBridgeStarted = false
                    do {
                        try await self.resolvedAgentClient().restart()
                        self.agentBridgeStarted = true
                        log("ChatProvider: agent bridge restarted with new Playwright settings")
                    } catch {
                        logError("Failed to restart agent bridge after Playwright setting change", error: error)
                    }
                }
            }

        // Keep groupedSessions in sync — runs off the hot path so SwiftUI body never recomputes it
        sessionGroupingObserver = Publishers.CombineLatest3($sessions, $searchQuery, $currentSession)
            .receive(on: RunLoop.main)
            .sink { [weak self] _, _, _ in
                guard let self else { return }
                self.groupedSessions = self.computeGroupedSessions()
            }

        // Kill agent bridge subprocess on app quit to prevent orphaned Node.js processes
        terminationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil, queue: .main
        ) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.resolvedAgentClient().stop()
            }
        }
    }

    private var terminationObserver: NSObjectProtocol?

    /// Pre-start the active bridge so the first query doesn't wait for process launch
    func warmupBridge() async {
        await preparePromptContextIfNeeded()
        _ = await ensureBridgeStarted()
    }

    /// Drop a cached agent surface so the next query recreates it with fresh prompt context.
    func invalidateAgentSurface(surface: AgentSurfaceReference) async {
        guard agentBridgeStarted else { return }
        await resolvedAgentClient().invalidateSurface(surface)
    }

    /// Test that the Playwright Chrome extension is connected and working.
    /// Ensures the bridge is started (restarting if needed to pick up new token),
    /// then sends a lightweight test query that triggers a browser_snapshot tool call.
    func testPlaywrightConnection() async throws -> Bool {
        // Don't restart bridge during a mode switch — caller should retry after switch completes
        guard !modeSwitchInProgress else {
            log("ChatProvider: testPlaywrightConnection skipped — mode switch in progress")
            return false
        }
        // Restart bridge to pick up new extension token
        agentBridgeStarted = false
        do {
            try await resolvedAgentClient().restart()
            agentBridgeStarted = true
        } catch {
            try await resolvedAgentClient().start()
            agentBridgeStarted = true
        }
        return try await resolvedAgentClient().testPlaywrightConnection()
    }

    /// Whether we're currently in user's Claude account mode
    private var isUserClaudeMode: Bool {
        bridgeMode == BridgeMode.userClaude.rawValue
    }

    /// Ensure the agent bridge is started (restarts if the process died).
    /// - Parameter fromModeSwitch: true when called from within switchBridgeMode,
    ///   which already holds modeSwitchInProgress. External callers (sendMessage)
    ///   pass false (the default) and will wait for any in-flight switch.
    func ensureBridgeStartedForKernel() async -> Bool {
        await ensureBridgeStarted()
    }

    private func ensureBridgeStarted(fromModeSwitch: Bool = false) async -> Bool {
        // Wait for any in-flight mode switch to finish before touching the bridge.
        // Without this, a query arriving mid-switch could restart the OLD bridge
        // with the wrong harness mode. Skipped when called from switchBridgeMode
        // itself (which holds the flag). External callers join the waiters array
        // and are woken when the switch (including warmup) completes — no timeout.
        while !fromModeSwitch && modeSwitchInProgress {
            log("ChatProvider: ensureBridgeStarted waiting for mode switch to complete")
            await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
                modeSwitchWaiters.append(c)
            }
        }
        if agentBridgeStarted {
            let alive = await resolvedAgentClient().isAlive
            if !alive {
                log("ChatProvider: agent bridge process died, will restart")
                agentBridgeStarted = false
            }
        }
        guard !agentBridgeStarted else { return true }
        // Wait for API keys (Firebase, Calendar) before starting the bridge.
        await APIKeyService.shared.waitForKeys()
        do {
            await preparePromptContextIfNeeded()
            try await resolvedAgentClient().start()
            agentBridgeStarted = true
            log("ChatProvider: agent bridge started successfully")
            // Set up global auth handlers so auth_required during warmup is handled
            await resolvedAgentClient().setGlobalAuthHandlers(
                onAuthRequired: { [weak self] methods, authUrl in
                    Task { @MainActor [weak self] in
                        self?.claudeAuthMethods = methods
                        self?.claudeAuthUrl = authUrl
                        self?.isClaudeAuthRequired = true
                    }
                },
                onAuthSuccess: { [weak self] in
                    Task { @MainActor [weak self] in
                        self?.isClaudeAuthRequired = false
                        self?.checkClaudeConnectionStatus()
                    }
                }
            )
            await kernelTurnProjection.attachClient(resolvedAgentClient())
            // Pre-warm ACP sessions with their respective system prompts.
            // This is the only place the system prompt is built and applied.
            let promptContext = formatMemoriesSection()
            let mainSystemPrompt = buildSystemPrompt(contextString: promptContext, style: .main)
            let floatingSystemPrompt = buildFloatingBarSystemPrompt(contextString: promptContext)
            let floatingPillSystemPrompt = buildFloatingBarSystemPrompt(
                contextString: promptContext,
                excludingToolNames: ["spawn_agent", "run_agent_and_wait"]
            )
            let floatingModel = ShortcutSettings.shared.selectedModel.isEmpty
                ? ModelQoS.Claude.defaultSelection
                : ShortcutSettings.shared.selectedModel
            cachedMainSystemPrompt = mainSystemPrompt
            cachedFloatingSystemPrompt = floatingSystemPrompt
            cachedFloatingPillSystemPrompt = floatingPillSystemPrompt
            // Hermes and OpenClaw ignore Omi's Claude model aliases, so leave
            // the model hint nil to avoid recording a model ID in binding metadata
            // that could trigger spurious context-changed sessions later.
            let usesNativeModelChoice = activeBridgeHarness == "hermes" || activeBridgeHarness == "openclaw"
            let mainWarmupModel = usesNativeModelChoice ? nil : ModelQoS.Claude.chat
            let floatingWarmupModel = usesNativeModelChoice ? nil : floatingModel
            await resolvedAgentClient().warmupSession(cwd: effectiveAgentWorkingDirectory(), sessions: [
                .init(key: "main", model: mainWarmupModel, systemPrompt: mainSystemPrompt),
                .init(key: "floating", model: floatingWarmupModel, systemPrompt: floatingSystemPrompt)
            ])
            return true
        } catch {
            logError("Failed to start agent bridge", error: error)
            let rawError = String(describing: error)
            AnalyticsManager.shared.chatAgentError(error: "AI not available: bridge failed to start", rawError: rawError)
            errorMessage = "AI not available: \(error.localizedDescription)"
            return false
        }
    }

    /// Ensures all prompt-backed local context is loaded before we build and cache the ACP session prompt.
    private func preparePromptContextIfNeeded() async {
        await warmupPromptContext()
    }

    private func resetSessionStateForAuthChange() {
        messages.removeAll()
        resetMessagesPagination()
        pendingAttachments.removeAll()
        sessions.removeAll()
        currentSession = nil
        cachedMemories = []
        memoriesLoaded = false
        cachedGoals = []
        goalsLoaded = false
        cachedTasks = []
        tasksLoaded = false
        cachedAIProfile = ""
        aiProfileLoaded = false
        cachedDatabaseSchema = ""
        schemaLoaded = false
        cachedMainSystemPrompt = ""
        cachedFloatingSystemPrompt = ""
        cachedFloatingPillSystemPrompt = ""
    }

    private var runtimeOwnerId: String? {
        AuthState.shared.userId ?? UserDefaults.standard.string(forKey: "auth_userId")
    }

    private func mainChatRuntimeChatId(sessionId: String?) -> String {
        guard let sessionId, !sessionId.isEmpty else {
            if let appId = selectedAppId, !appId.isEmpty {
                return "default|\(appId)"
            }
            return "default"
        }
        return sessionId
    }

    private func querySurface(
        surfaceRef: AgentSurfaceReference?,
        sessionId: String?,
        systemPromptStyle: ChatSystemPromptStyle
    ) -> AgentSurfaceReference {
        if let surfaceRef {
            return surfaceRef
        }
        if isOnboarding {
            return .onboarding()
        }
        if systemPromptStyle == .floating {
            return mainChatSurfaceReference()
        }
        return .mainChat(chatId: mainChatRuntimeChatId(sessionId: sessionId))
    }

    private static let conversationTurnBackfillKey = "conversationTurnBackfill_v1"

    private func backfillConversationTurnsIfNeeded(for surface: AgentSurfaceReference) async {
        let ownerId = runtimeOwnerId ?? "unknown"
        let key = "\(Self.conversationTurnBackfillKey).\(ownerId).\(surface.key)"
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        let recent = messages
            .filter { !$0.copyableText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !$0.isStreaming }
            .suffix(50)
        guard !recent.isEmpty else { return }
        let turns = recent.map { message in
            (
                role: message.sender == .user ? "user" : "assistant",
                content: message.copyableText,
                createdAtMs: Int(message.createdAt.timeIntervalSince1970 * 1_000)
            )
        }
        await resolvedAgentClient().importConversationTurns(surface: surface, turns: turns)
        UserDefaults.standard.set(true, forKey: key)
    }

    private func isFloatingPillSurface(_ surface: AgentSurfaceReference) -> Bool {
        surface.surfaceKind == "floating_bar" && surface.externalRefKind == "pill"
    }

    /// Switch between bridge modes (Omi AI via piMono, or user's Claude OAuth)
    func switchBridgeMode(to mode: BridgeMode) async {
        // Normalize legacy omiAI to piMono
        let resolvedMode: BridgeMode = (mode == .omiAI) ? .piMono : mode
        let newHarness = Self.harnessMode(for: resolvedMode)
        let previousHarness = activeBridgeHarness
        // Compare against the actual running harness, NOT @AppStorage (which may
        // already reflect the new value because another view wrote the same key).
        guard newHarness != previousHarness else { return }

        // Serialize overlapping switches. The SettingsPage picker fires onChange
        // in a new Task on each toggle, so rapid A→B→A→B can overlap multiple calls.
        // Without serialization, overlapping calls could overwrite agentClient and
        // leak intermediate bridge processes. Loop re-checks after waking because
        // another waiter may have started a new switch before this one resumes.
        while modeSwitchInProgress {
            log("ChatProvider: switchBridgeMode waiting for in-flight switch to finish")
            await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
                modeSwitchWaiters.append(c)
            }
        }

        // Re-check after waiting — the in-flight switch may have already reached
        // the same target mode we wanted.
        guard newHarness != activeBridgeHarness else { return }

        log("ChatProvider: Switching bridge mode from \(activeBridgeHarness) to \(resolvedMode.rawValue)")

        // Update activeBridgeHarness immediately so a rapid second flip (e.g. user
        // toggles back before the first switch finishes) sees the correct target
        // mode in the guard above and doesn't no-op incorrectly.
        activeBridgeHarness = newHarness

        // Block queries during the transition so sendMessage doesn't race and
        // restart the OLD bridge while we're replacing it.
        modeSwitchInProgress = true

        // Stop the current bridge and wait for the subprocess to fully terminate.
        // This is critical: without the wait, the old Node.js process can still be
        // alive when the new one starts, causing log confusion and session reuse.
        await resolvedAgentClient().stopAndWaitForExit()
        agentBridgeStarted = false

        // Switch mode and recreate client session
        bridgeMode = resolvedMode.rawValue
        agentClient = AgentClient.makeSession(harnessMode: newHarness)
        AnalyticsManager.shared.chatBridgeModeChanged(from: previousHarness, to: resolvedMode.rawValue)

        // Check Claude connection status when switching to user's Claude account
        if mode == .userClaude {
            checkClaudeConnectionStatus()
        }

        // Warm up the new bridge. Keep modeSwitchInProgress = true so external
        // callers (sendMessage) block until warmup completes. Pass fromModeSwitch
        // so ensureBridgeStarted skips its own mode-switch wait.
        let started = await ensureBridgeStarted(fromModeSwitch: true)
        log("ChatProvider: Bridge mode switch complete — \(resolvedMode.rawValue) started=\(started)")

        // Unblock queries and wake all waiting switches now that the bridge
        // is fully started and warmed.
        modeSwitchInProgress = false
        let waiters = modeSwitchWaiters
        modeSwitchWaiters.removeAll()
        for waiter in waiters { waiter.resume() }
    }

    /// Start Claude OAuth authentication (Mode B)
    /// Opens the OAuth URL (provided by the bridge) in the default browser.
    /// The bridge handles the full OAuth flow: local callback server, token exchange,
    /// credential storage, and ACP subprocess restart.
    func startClaudeAuth() {
        guard isUserClaudeMode else { return }

        if let urlString = claudeAuthUrl, let url = URL(string: urlString) {
            log("ChatProvider: Opening Claude OAuth URL in browser")
            NSWorkspace.shared.open(url)
        } else {
            logError("ChatProvider: No auth URL available from bridge")
            isClaudeAuthRequired = false
        }
    }

    /// Check whether a cached Claude OAuth token exists (config file or Keychain)
    func checkClaudeConnectionStatus() {
        // Check config file
        let configPath = NSString(string: "~/Library/Application Support/Claude/config.json").expandingTildeInPath
        if FileManager.default.fileExists(atPath: configPath),
           let data = FileManager.default.contents(atPath: configPath),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let tokenCache = json["oauth:tokenCache"] as? String, !tokenCache.isEmpty {
            isClaudeConnected = true
            return
        }

        // Check Keychain via security CLI (Keychain item owned by Claude Desktop)
        let secProcess = Process()
        secProcess.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        secProcess.arguments = ["find-generic-password", "-s", "Claude Code-credentials"]
        secProcess.standardOutput = FileHandle.nullDevice
        secProcess.standardError = FileHandle.nullDevice
        do {
            try secProcess.run()
            secProcess.waitUntilExit()
            isClaudeConnected = (secProcess.terminationStatus == 0)
        } catch {
            isClaudeConnected = false
        }
    }

    /// Disconnect from Claude: clear OAuth token, switch back to free mode via serialized path
    func disconnectClaude() async {
        log("ChatProvider: Disconnecting Claude account")

        // 1. Clear the OAuth token from config file
        let configPath = NSString(string: "~/Library/Application Support/Claude/config.json").expandingTildeInPath
        if let data = FileManager.default.contents(atPath: configPath),
           var json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            json.removeValue(forKey: "oauth:tokenCache")
            if let updatedData = try? JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .sortedKeys]) {
                try? updatedData.write(to: URL(fileURLWithPath: configPath))
            }
        }

        // 2. Clear OAuth credentials from macOS Keychain
        //    The Keychain item is owned by Claude Desktop/CLI, so SecItemDelete fails
        //    with errSecInvalidOwnerEdit. Use the `security` CLI which runs as the user.
        let secProcess = Process()
        secProcess.executableURL = URL(fileURLWithPath: "/usr/bin/security")
        secProcess.arguments = ["delete-generic-password", "-s", "Claude Code-credentials"]
        secProcess.standardOutput = FileHandle.nullDevice
        secProcess.standardError = FileHandle.nullDevice
        do {
            try secProcess.run()
            secProcess.waitUntilExit()
            if secProcess.terminationStatus == 0 {
                log("ChatProvider: Cleared Claude Code credentials from Keychain")
            } else {
                log("ChatProvider: No Claude Code credentials found in Keychain (status=\(secProcess.terminationStatus))")
            }
        } catch {
            log("ChatProvider: Failed to run security command: \(error.localizedDescription)")
        }

        // 3. Update state
        isClaudeConnected = false

        // 4. Switch back to piMono through the serialized switchBridgeMode path
        //    so all bridge lifecycle state (activeBridgeHarness, modeSwitchInProgress,
        //    waiters) stays consistent.
        await switchBridgeMode(to: .piMono)
    }

    // MARK: - Session Management

    /// Fetch all chat sessions for the current app (retries up to 3 times on failure)
    func fetchSessions() async {
        isLoadingSessions = true
        defer { isLoadingSessions = false }

        let maxAttempts = 3
        let delays: [UInt64] = [1_000_000_000, 2_000_000_000] // 1s, 2s
        var lastError: Error?

        for attempt in 1...maxAttempts {
            do {
                sessions = try await APIClient.shared.getChatSessions(
                    appId: selectedAppId,
                    starred: showStarredOnly ? true : nil
                )
                log("ChatProvider loaded \(sessions.count) sessions (starred filter: \(showStarredOnly))")
                sessionsLoadError = nil

                // If we have sessions and no current session, select the most recent
                if currentSession == nil, let mostRecent = sessions.first {
                    await selectSession(mostRecent)
                }
                return
            } catch {
                lastError = error
                logError("Failed to load chat sessions (attempt \(attempt)/\(maxAttempts))", error: error)
                if attempt < maxAttempts {
                    try? await Task.sleep(nanoseconds: delays[attempt - 1])
                }
            }
        }

        sessions = []
        sessionsLoadError = lastError?.localizedDescription ?? "Failed to load chats. Check your connection and try again."
    }

    /// Toggle the starred filter and reload sessions
    func toggleStarredFilter() async {
        showStarredOnly.toggle()
        log("Toggled starred filter: \(showStarredOnly)")
        AnalyticsManager.shared.chatStarredFilterToggled(enabled: showStarredOnly)
        await fetchSessions()
    }

    /// Create a new chat session
    /// - Parameters:
    ///   - title: Optional session title
    ///   - skipGreeting: Skip the initial AI greeting message
    ///   - appId: Override app ID (e.g. "task-chat" to isolate task sessions from default chat)
    func createNewSession(title: String? = nil, skipGreeting: Bool = false, appId: String? = nil) async -> ChatSession? {
        do {
            let session = try await APIClient.shared.createChatSession(title: title, appId: appId ?? selectedAppId)
            sessions.insert(session, at: 0)
            currentSession = session
            isInDefaultChat = false
            messages = []
            resetMessagesPagination()
            log("Created new chat session: \(session.id)")
            AnalyticsManager.shared.chatSessionCreated()

            // Generate initial greeting message (skip for task chats that send their own context)
            if !skipGreeting {
                await fetchInitialMessage(for: session)
            }

            return session
        } catch {
            logError("Failed to create chat session", error: error)
            errorMessage = "Failed to create new chat"
            return nil
        }
    }

    /// Fetch and display an initial greeting message for a new session
    private func fetchInitialMessage(for session: ChatSession) async {
        do {
            let response = try await APIClient.shared.getInitialMessage(
                sessionId: session.id,
                appId: selectedAppId
            )

            // Add the AI greeting to messages (already has server ID)
            let greetingMessage = ChatMessage(
                id: response.messageId,
                text: response.message,
                createdAt: Date(),
                sender: .ai,
                isStreaming: false,
                rating: nil,
                isSynced: true
            )
            messages.append(greetingMessage)

            // Update session preview
            if let index = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[index].preview = response.message
            }

            // Track analytics
            AnalyticsManager.shared.initialMessageGenerated(hasApp: selectedAppId != nil)

            log("Added initial greeting message for session \(session.id)")
        } catch {
            // Non-fatal: session still works without greeting
            logError("Failed to fetch initial message", error: error)
        }
    }

    /// Select a session and load its messages
    func selectSession(_ session: ChatSession, force: Bool = false) async {
        guard force || currentSession?.id != session.id || isInDefaultChat else { return }

        currentSession = session
        isInDefaultChat = false
        isLoading = true
        errorMessage = nil
        hasMoreMessages = false

        do {
            let persistedMessages = try await APIClient.shared.getMessages(
                sessionId: session.id,
                limit: messagesPageSize
            )
            messages = persistedMessages.map(ChatMessage.init(from:))
                .sorted(by: { $0.createdAt < $1.createdAt })
            await rehydrateMissingArtifactResourcesFromKernel()
            messagesPaginationOffset = persistedMessages.count
            // If we got a full page, there might be more messages
            hasMoreMessages = persistedMessages.count == messagesPageSize
            log("ChatProvider loaded \(messages.count) messages for session \(session.id), hasMore: \(hasMoreMessages)")
        } catch {
            logError("Failed to load messages for session", error: error)
            messages = []
            resetMessagesPagination()
        }

        isLoading = false
    }

    /// Load more (older) messages for the current session
    func loadMoreMessages() async {
        guard hasMoreMessages,
              !isLoadingMoreMessages else { return }

        isLoadingMoreMessages = true

        do {
            // A burst of live messages (e.g. from another device) shifts the
            // newest-first window, so a fetched page can dedupe entirely to
            // messages we already hold. Consume up to a few windows per call so
            // one user action always yields visible progress; the cursor
            // advances every iteration, so this terminates. Deliberately NOT
            // derived from the local message count — overcounting (deletions,
            // polling gaps) would overshoot and silently skip history, while a
            // duplicate window only costs a redundant fetch.
            var appendedCount = 0
            var existingIds = Set(messages.map(\.id))
            for _ in 0..<3 {
                let offset = messagesPaginationOffset
                let olderMessages: [ChatMessageDB]
                if let sessionId = currentSessionId {
                    olderMessages = try await APIClient.shared.getMessages(
                        sessionId: sessionId,
                        limit: messagesPageSize,
                        offset: offset
                    )
                } else {
                    olderMessages = try await APIClient.shared.getMessages(
                        appId: selectedAppId,
                        limit: messagesPageSize,
                        offset: offset
                    )
                }

                // Advance by raw records consumed — even when dedupe below drops
                // some — so the next request can never re-issue the same window.
                messagesPaginationOffset += olderMessages.count

                // Drop the window overlap before appending.
                let newMessages = olderMessages.map(ChatMessage.init(from:))
                    .filter { !existingIds.contains($0.id) }
                existingIds.formUnion(newMessages.map(\.id))

                // Append older messages and re-sort to ensure correct chronological order
                if !newMessages.isEmpty {
                    messages.append(contentsOf: newMessages)
                    messages.sort(by: { $0.createdAt < $1.createdAt })
                }
                appendedCount += newMessages.count

                // Check if there are more (based on the raw page size, pre-dedupe)
                hasMoreMessages = olderMessages.count == messagesPageSize
                if appendedCount > 0 || !hasMoreMessages { break }
            }
            log("Loaded \(appendedCount) more messages, total: \(messages.count), hasMore: \(hasMoreMessages)")
        } catch {
            logError("Failed to load more messages", error: error)
        }

        isLoadingMoreMessages = false
    }

    /// Track which sessions are currently being deleted
    @Published var deletingSessionIds: Set<String> = []

    /// Delete a chat session
    func deleteSession(_ session: ChatSession) async {
        deletingSessionIds.insert(session.id)
        do {
            try await APIClient.shared.deleteChatSession(sessionId: session.id)
            deletingSessionIds.remove(session.id)
            sessions.removeAll { $0.id == session.id }

            // If deleted the current session, select another or clear
            if currentSession?.id == session.id {
                if let nextSession = sessions.first {
                    await selectSession(nextSession)
                } else {
                    currentSession = nil
                    messages = []
                    resetMessagesPagination()
                }
            }

            log("Deleted chat session: \(session.id)")
            AnalyticsManager.shared.chatSessionDeleted()
        } catch {
            deletingSessionIds.remove(session.id)
            logError("Failed to delete chat session", error: error)
            errorMessage = "Failed to delete chat"
        }
    }

    /// Toggle starred status for a session
    func toggleStarred(_ session: ChatSession) async {
        do {
            let updated = try await APIClient.shared.updateChatSession(
                sessionId: session.id,
                starred: !session.starred
            )

            // Update in sessions list
            if let index = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[index] = updated
            }

            // Update current session if it's the same
            if currentSession?.id == session.id {
                currentSession = updated
            }

            log("Toggled starred for session \(session.id): \(updated.starred)")
        } catch {
            logError("Failed to toggle starred", error: error)
        }
    }

    /// Update session title (user-initiated rename)
    func updateSessionTitle(_ session: ChatSession, title: String) async {
        do {
            let updated = try await APIClient.shared.updateChatSession(
                sessionId: session.id,
                title: title
            )

            // Update in sessions list
            if let index = sessions.firstIndex(where: { $0.id == session.id }) {
                sessions[index] = updated
            }

            // Update current session if it's the same
            if currentSession?.id == session.id {
                currentSession = updated
            }

            log("Updated title for session \(session.id): \(title)")
            AnalyticsManager.shared.sessionRenamed()
        } catch {
            logError("Failed to update session title", error: error)
        }
    }

    // MARK: - Load Context (Memories)

    /// Loads user memories from local SQLite for use in prompts (refreshed each turn).
    private func refreshMemoriesForPrompt() async {
        do {
            cachedMemories = try await MemoryStorage.shared.getLocalMemories(limit: 50)
            memoriesLoaded = true
            log("ChatProvider refreshed \(cachedMemories.count) memories from local DB")
        } catch {
            logError("Failed to load memories from local DB", error: error)
            // Continue without memories - non-critical
        }
    }

    /// Formats cached memories into a string for the prompt
    private func formatMemoriesSection() -> String {
        guard !cachedMemories.isEmpty else { return "" }

        let userName = AuthService.shared.displayName.isEmpty ? "the user" : AuthService.shared.givenName

        var lines: [String] = ["<user_facts>", "Facts about \(userName):"]
        for memory in cachedMemories.prefix(30) {  // Limit to 30 most relevant
            lines.append("- [memory] \(memory.content)")
        }
        lines.append("</user_facts>")

        return lines.joined(separator: "\n")
    }

    // MARK: - Load Goals

    /// Loads user goals from local SQLite for use in prompts
    private func loadGoalsIfNeeded() async {
        guard !goalsLoaded else { return }

        do {
            cachedGoals = try await GoalStorage.shared.getLocalGoals(activeOnly: false)
            goalsLoaded = true
            log("ChatProvider loaded \(cachedGoals.count) goals from local DB")
        } catch {
            logError("Failed to load goals for chat context", error: error)
        }
    }

    /// Formats goals into a prompt section
    private func formatGoalSection() -> String {
        let activeGoals = cachedGoals.filter { $0.isActive }
        guard !activeGoals.isEmpty else { return "" }

        var lines: [String] = ["\n<user_goals>"]
        for goal in activeGoals {
            var line = "- \(goal.title)"
            if let desc = goal.description, !desc.isEmpty {
                line += ": \(desc)"
            }
            if goal.goalType != .boolean {
                line += " (progress: \(Int(goal.currentValue))/\(Int(goal.targetValue))"
                if let unit = goal.unit, !unit.isEmpty { line += " \(unit)" }
                line += ")"
            }
            lines.append(line)
        }
        lines.append("</user_goals>")
        return lines.joined(separator: "\n")
    }

    // MARK: - Load Tasks

    /// Fetches the latest 20 active tasks from local database for context
    private func loadTasksIfNeeded() async {
        guard !tasksLoaded else { return }

        do {
            cachedTasks = try await ActionItemStorage.shared.getLocalActionItems(
                limit: 20,
                completed: false
            )
            tasksLoaded = true
            log("ChatProvider loaded \(cachedTasks.count) tasks for context")
        } catch {
            logError("Failed to load tasks for chat context", error: error)
            tasksLoaded = true
        }
    }

    /// Formats cached tasks into a prompt section
    private func formatTasksSection() -> String {
        guard !cachedTasks.isEmpty else { return "" }

        var lines: [String] = ["\n<user_tasks>", "Current tasks:"]
        for task in cachedTasks {
            var line = "- \(task.description)"
            if let priority = task.priority {
                line += " [priority: \(priority)]"
            }
            if let dueAt = task.dueAt {
                let formatter = DateFormatter()
                formatter.dateStyle = .short
                formatter.timeStyle = .short
                line += " [due: \(formatter.string(from: dueAt))]"
            }
            if let category = task.category {
                line += " [category: \(category)]"
            }
            lines.append(line)
        }
        lines.append("</user_tasks>")
        return lines.joined(separator: "\n")
    }

    // MARK: - Load AI User Profile

    /// Fetches the latest AI-generated user profile from local database
    private func loadAIProfileIfNeeded() async {
        guard !aiProfileLoaded else { return }

        if let profile = await AIUserProfileService.shared.getLatestProfile() {
            cachedAIProfile = profile.profileText
            log("ChatProvider loaded AI profile (generated \(profile.generatedAt))")
        }
        aiProfileLoaded = true
    }

    /// Formats AI profile into a prompt section
    private func formatAIProfileSection() -> String {
        guard !cachedAIProfile.isEmpty else { return "" }
        return "\n<ai_user_profile>\n\(cachedAIProfile)\n</ai_user_profile>"
    }

    // MARK: - Load Database Schema

    /// Queries sqlite_master to build an up-to-date schema description for the prompt
    private func loadSchemaIfNeeded() async {
        guard !schemaLoaded else { return }

        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
            log("ChatProvider: database not available for schema introspection")
            schemaLoaded = true
            return
        }

        do {
            let tables = try await dbQueue.read { db -> [(name: String, sql: String)] in
                let rows = try Row.fetchAll(db, sql: """
                    SELECT name, sql FROM sqlite_master
                    WHERE type='table' AND sql IS NOT NULL
                    ORDER BY name
                """)
                return rows.compactMap { row -> (name: String, sql: String)? in
                    guard let name: String = row["name"],
                          let sql: String = row["sql"] else { return nil }
                    return (name: name, sql: sql)
                }
            }

            cachedDatabaseSchema = formatSchema(tables: tables)
            schemaLoaded = true
            log("ChatProvider loaded schema for \(tables.count) tables")
        } catch {
            logError("Failed to load database schema", error: error)
            schemaLoaded = true
        }
    }

    /// Formats raw DDL into a compact, LLM-friendly schema block
    private func formatSchema(tables: [(name: String, sql: String)]) -> String {
        var lines: [String] = ["**Database schema (omi.db):**", ""]

        for (name, sql) in tables {
            // Skip internal tables
            if ChatPrompts.excludedTables.contains(name) { continue }
            if ChatPrompts.excludedTablePrefixes.contains(where: { name.hasPrefix($0) }) { continue }
            // Skip FTS virtual and shadow tables — documented in schemaFooter with MATCH patterns instead
            if name.contains("_fts") { continue }

            // Extract column names only, stripping types, constraints, and infrastructure columns
            let columnNames = extractColumns(from: sql).compactMap { col -> String? in
                let name = col.components(separatedBy: .whitespaces).first?
                    .trimmingCharacters(in: CharacterSet(charactersIn: "\"'`")) ?? ""
                return ChatPrompts.excludedColumns.contains(name) ? nil : name
            }.filter { !$0.isEmpty }
            guard !columnNames.isEmpty else { continue }

            // Table header with annotation
            let annotation = ChatPrompts.tableAnnotations[name] ?? ""
            let header = annotation.isEmpty ? name : "\(name) — \(annotation)"
            lines.append(header)

            // Columns with annotations (key columns get descriptions, others are just names)
            let tableAnnotations = ChatPrompts.columnAnnotations[name] ?? [:]
            if tableAnnotations.isEmpty {
                lines.append("  \(columnNames.joined(separator: ", "))")
            } else {
                let annotated = columnNames.map { col in
                    if let desc = tableAnnotations[col] {
                        return "\(col) — \(desc)"
                    }
                    return col
                }
                lines.append("  \(annotated.joined(separator: ", "))")
            }
            lines.append("")
        }

        // Append FTS documentation, relationships, and footer
        lines.append(ChatPrompts.schemaFooter)

        return lines.joined(separator: "\n")
    }

    /// Extracts column definitions from a CREATE TABLE SQL statement
    /// Produces compact representations like: "id INTEGER PRIMARY KEY", "name TEXT NOT NULL"
    private func extractColumns(from sql: String) -> [String] {
        // Find content between first ( and last )
        guard let openParen = sql.firstIndex(of: "("),
              let closeParen = sql.lastIndex(of: ")") else { return [] }

        let body = String(sql[sql.index(after: openParen)..<closeParen])

        // Split by commas, but respect parentheses (for REFERENCES(...) etc.)
        var columns: [String] = []
        var current = ""
        var depth = 0
        for char in body {
            if char == "(" { depth += 1 }
            else if char == ")" { depth -= 1 }

            if char == "," && depth == 0 {
                let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty { columns.append(trimmed) }
                current = ""
            } else {
                current.append(char)
            }
        }
        let trimmed = current.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty { columns.append(trimmed) }

        // Filter out table constraints (UNIQUE, CHECK, FOREIGN KEY, etc.) — keep only column defs
        return columns.filter { col in
            let upper = col.uppercased().trimmingCharacters(in: .whitespaces)
            return !upper.hasPrefix("UNIQUE") && !upper.hasPrefix("CHECK") &&
                   !upper.hasPrefix("FOREIGN") && !upper.hasPrefix("CONSTRAINT") &&
                   !upper.hasPrefix("PRIMARY KEY")
        }.map { col in
            // Normalize whitespace
            col.components(separatedBy: .whitespacesAndNewlines)
                .filter { !$0.isEmpty }
                .joined(separator: " ")
        }
    }

    // MARK: - Build System Prompt with Variables

    /// Builds the system prompt for ACP session initialization.
    /// Called once at warmup (via ensureBridgeStarted) and cached in cachedMainSystemPrompt.
    /// Conversation history is injected here so the brand-new ACP session starts with context
    /// from before the app launch. After session/new the ACP SDK owns history natively.
    /// Display name for prompts, with a stable fallback — one source so the
    /// cached static prefix and the live-context tail never disagree.
    private var promptUserName: String {
        AuthService.shared.displayName.isEmpty ? "there" : AuthService.shared.givenName
    }

    /// When `staticBody` is true, build a cache-friendly prefix with no live data:
    /// the datetime is blanked and the memories fallback is skipped, because the
    /// live context is appended separately after the cache-split sentinel.
    private func buildSystemPrompt(contextString: String, style: ChatSystemPromptStyle, staticBody: Bool = false) -> String {
        let userName = promptUserName

        // Backend context (memories + conversations); fall back to local memories
        // when empty — unless building the static body (live data lives in the tail).
        let contextSection = (contextString.isEmpty && !staticBody) ? formatMemoriesSection() : contextString

        // Build individual sections
        let goalSection = formatGoalSection()
        let tasksSection = formatTasksSection()
        let aiProfileSection = formatAIProfileSection()

        // Build base prompt with goals, AI profile, and dynamic schema
        var prompt = ChatPromptBuilder.buildDesktopChat(
            userName: userName,
            memoriesSection: contextSection,
            goalSection: goalSection,
            tasksSection: tasksSection,
            aiProfileSection: aiProfileSection,
            databaseSchema: style.includesDatabaseSchema ? cachedDatabaseSchema : "",
            currentDatetime: staticBody ? "" : nil
        )

        // Append global CLAUDE.md instructions if enabled
        if claudeMdEnabled, let claudeMd = claudeMdContent {
            prompt += "\n\n<claude_md>\n\(claudeMd)\n</claude_md>"
        }

        // Append project CLAUDE.md instructions if enabled
        if projectClaudeMdEnabled, let projectClaudeMd = projectClaudeMdContent {
            prompt += "\n\n<project_claude_md>\n\(projectClaudeMd)\n</project_claude_md>"
        }

        // Append enabled skills as available context (global + project)
        let enabledSkillNames = getEnabledSkillNames()
        if style.includesSkills && !enabledSkillNames.isEmpty {
            let allSkills = discoveredSkills + projectDiscoveredSkills
            let skillNames = allSkills
                .filter { enabledSkillNames.contains($0.name) && ($0.name != "dev-mode" || devModeEnabled) }
                .map { $0.name }
                .joined(separator: ", ")
            if !skillNames.isEmpty {
                prompt += "\n\n<available_skills>\nAvailable skills: \(skillNames)\nUse the load_skill tool to get full instructions for any skill before using it.\n</available_skills>"
            }
        }

        // Log prompt context summary
        let activeGoalCount = cachedGoals.filter { $0.isActive }.count
        let historyMessages = messages.filter { !$0.text.isEmpty && !$0.isStreaming }
        let historyCount = min(historyMessages.count, 20)
        log("ChatProvider: prompt built — schema: \(style.includesDatabaseSchema && !cachedDatabaseSchema.isEmpty ? "yes" : "no"), goals: \(activeGoalCount), tasks: \(cachedTasks.count), ai_profile: \(!cachedAIProfile.isEmpty ? "yes" : "no"), memories: \(cachedMemories.count), history: kernel-owned, claude_md: \(claudeMdEnabled && claudeMdContent != nil ? "yes" : "no"), project_claude_md: \(projectClaudeMdEnabled && projectClaudeMdContent != nil ? "yes" : "no"), skills: \(style.includesSkills ? enabledSkillNames.count : 0), dev_mode_in_skills: \(style.includesSkills && devModeEnabled && devModeContext != nil ? "yes" : "no"), prompt_length: \(prompt.count) chars")

        // Log per-section character breakdown
        let baseTemplate = ChatPromptBuilder.buildDesktopChat(
            userName: userName, memoriesSection: "", goalSection: "", tasksSection: "", aiProfileSection: "", databaseSchema: "")
        let allSkillsForSize = (discoveredSkills + projectDiscoveredSkills)
            .filter { enabledSkillNames.contains($0.name) && ($0.name != "dev-mode" || devModeEnabled) }
            .map { $0.name }.joined(separator: ", ")
        let skillsSectionSize = allSkillsForSize.isEmpty ? 0 : allSkillsForSize.count + 80 // names + wrapper
        log("ChatProvider: prompt breakdown — " +
            "base_template:\(baseTemplate.count)c, " +
            "context:\(contextSection.count)c, " +
            "goals:\(goalSection.count)c, " +
            "tasks:\(tasksSection.count)c, " +
            "ai_profile:\(aiProfileSection.count)c, " +
            "schema:\(style.includesDatabaseSchema ? cachedDatabaseSchema.count : 0)c, " +
            "history:kernel-owned, " +
            "claude_md:\(claudeMdContent?.count ?? 0)c, " +
            "project_claude_md:\(projectClaudeMdContent?.count ?? 0)c, " +
            "skills:\(style.includesSkills ? skillsSectionSize : 0)c")

        return prompt
    }

    /// Sentinel separating the static (cacheable) system prefix from the
    /// per-conversation live context. The Rust chat proxy splits on this so the
    /// `cache_control` breakpoint covers only the stable prefix. Must match
    /// `SYSTEM_CACHE_SPLIT` in `Backend-Rust/src/routes/chat_completions.rs`.
    static let cacheSplitSentinel = "<<<OMI_CACHE_SPLIT_V1>>>"

    private func buildFloatingBarSystemPrompt(
        contextString: String,
        excludingToolNames excludedToolNames: Set<String> = []
    ) -> String {
        // Cache-friendly split: the static prefix is byte-identical across
        // conversations (so the proxy can cache it); volatile data — datetime,
        // memories, screen — goes in the live tail after the sentinel, which the
        // proxy leaves uncached. See SYSTEM_CACHE_SPLIT in chat_completions.rs.
        var staticBody = buildSystemPrompt(contextString: "", style: .floating, staticBody: true)
        if !excludedToolNames.isEmpty {
            let fullToolPrompt = DesktopCapabilityRegistry.desktopToolPrompt
                .replacingOccurrences(of: "{user_name}", with: promptUserName)
            let scopedToolPrompt = DesktopCapabilityRegistry.scopedDesktopToolPrompt(excluding: excludedToolNames)
                .replacingOccurrences(of: "{user_name}", with: promptUserName)
            staticBody = staticBody.replacingOccurrences(
                of: fullToolPrompt,
                with: scopedToolPrompt
            )
        }
        let staticPrefix = Self.floatingBarSystemPromptPrefix + "\n\n"
            + staticBody

        let tz = TimeZone.current.identifier
        var live = "<live_context>\nCurrent date/time in \(promptUserName)'s timezone (\(tz)): "
            + ChatPromptBuilder.currentDatetimeString()
        if !contextString.isEmpty {
            live += "\n\(contextString)"
        }
        live += "\n</live_context>"

        return staticPrefix + "\n\n" + Self.cacheSplitSentinel + "\n\n" + live
    }

    /// Build system prompt for task chat sessions.
    func buildTaskChatSystemPrompt() -> String {
        let userName = promptUserName
        let contextSection = formatMemoriesSection()
        let goalSection = formatGoalSection()
        let tasksSection = formatTasksSection()
        let aiProfileSection = formatAIProfileSection()

        var prompt = ChatPromptBuilder.buildDesktopChat(
            userName: userName,
            memoriesSection: contextSection,
            goalSection: goalSection,
            tasksSection: tasksSection,
            aiProfileSection: aiProfileSection,
            databaseSchema: cachedDatabaseSchema
        )

        // NO conversation_history — SDK handles this via resume

        if claudeMdEnabled, let claudeMd = claudeMdContent {
            prompt += "\n\n<claude_md>\n\(claudeMd)\n</claude_md>"
        }
        if projectClaudeMdEnabled, let projectClaudeMd = projectClaudeMdContent {
            prompt += "\n\n<project_claude_md>\n\(projectClaudeMd)\n</project_claude_md>"
        }

        let enabledSkillNames = getEnabledSkillNames()
        if !enabledSkillNames.isEmpty {
            let allSkills = discoveredSkills + projectDiscoveredSkills
            let skillNames = allSkills
                .filter { enabledSkillNames.contains($0.name) && ($0.name != "dev-mode" || devModeEnabled) }
                .map { $0.name }
                .joined(separator: ", ")
            if !skillNames.isEmpty {
                prompt += "\n\n<available_skills>\nAvailable skills: \(skillNames)\nUse the load_skill tool to get full instructions for any skill before using it.\n</available_skills>"
            }
        }

        log("ChatProvider: task chat prompt built — prompt_length: \(prompt.count) chars")
        return prompt
    }

    /// Builds system prompt using cached memories only (for simple messages)
    private func buildSystemPromptSimple() -> String {
        let userName = promptUserName
        let memoriesSection = formatMemoriesSection()

        return ChatPromptBuilder.buildDesktopChat(
            userName: userName,
            memoriesSection: memoriesSection
        )
    }


    // MARK: - Chat Lab Helpers

    /// Build a system prompt for the Chat Lab using a custom template but real user context.
    func labBuildSystemPrompt(floatingPrefix: String, mainTemplate: String) -> String {
        let userName = AuthService.shared.displayName.isEmpty ? "User" : AuthService.shared.givenName

        var prompt = floatingPrefix + "\n\n" + mainTemplate
        prompt = prompt.replacingOccurrences(of: "{user_name}", with: userName)
        prompt = prompt.replacingOccurrences(of: "{tz}", with: TimeZone.current.identifier)

        prompt = prompt.replacingOccurrences(
            of: "{current_datetime_str}", with: ChatPromptBuilder.currentDatetimeString())

        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.timeZone = TimeZone.current
        prompt = prompt.replacingOccurrences(of: "{current_datetime_iso}", with: isoFormatter.string(from: Date()))

        let utcFormatter = DateFormatter()
        utcFormatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        utcFormatter.timeZone = TimeZone(identifier: "UTC")
        prompt = prompt.replacingOccurrences(of: "{current_datetime_utc}", with: utcFormatter.string(from: Date()))

        prompt = prompt.replacingOccurrences(of: "{memories_section}", with: formatMemoriesSection())
        prompt = prompt.replacingOccurrences(of: "{goal_section}", with: formatGoalSection())
        prompt = prompt.replacingOccurrences(of: "{tasks_section}", with: formatTasksSection())
        prompt = prompt.replacingOccurrences(of: "{ai_profile_section}", with: formatAIProfileSection())
        prompt = prompt.replacingOccurrences(of: "{database_schema}", with: cachedDatabaseSchema)

        return prompt
    }

    /// Run a single question through the agent bridge for Chat Lab evaluation.
    /// Uses a unique session key so it doesn't interfere with the real chat.
    func labRunQuestion(question: String, systemPrompt: String, labSessionId: String) async -> String {
        // Ensure bridge is running
        guard await ensureBridgeStarted() else {
            return "[Bridge not available]"
        }

        do {
            let currentChatMode = chatMode
            let result = try await resolvedAgentClient().query(
                prompt: question,
                systemPrompt: systemPrompt,
                surface: .chatLab(labSessionId: labSessionId),
                model: ModelQoS.Claude.chatLabQuery,
                onTextDelta: { _ in },
                onToolCall: { callId, name, input in
                    let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
                    let result = await ChatToolExecutor.execute(toolCall, originatingChatMode: currentChatMode)
                    log("ChatLab: tool \(name) executed")
                    return result
                },
                onToolActivity: { _, _, _, _ in },
                onThinkingDelta: { _ in }
            )
            return result.text
        } catch {
            log("ChatLab: query error: \(error)")
            return "[Error: \(error.localizedDescription)]"
        }
    }

    /// Initialize chat: fetch sessions and load messages
    func initialize() async {
        await initializeVisibleMessages()
        await warmupPromptContext()
    }

    /// Load the chat state that is directly visible in Dashboard/Chat without warming prompt-only context.
    func initializeVisibleMessages() async {
        // Seed cumulative Omi AI cost from backend now that auth is ready (background, no latency)
        Task.detached(priority: .background) { [weak self] in
            guard let serverCost = await APIClient.shared.fetchTotalOmiAICost() else { return }
            guard let self else { return }
            // Make sure the user's plan is known before deciding whether to nudge —
            // otherwise a cold plan cache could flash the upgrade alert at a paid user.
            await FloatingBarUsageLimiter.shared.fetchPlan()
            await MainActor.run {
                // Always trust the server value — it's the authoritative total
                self.omiAICumulativeCostUsd = serverCost
                log("ChatProvider: Seeded Omi AI cumulative cost from backend: $\(String(format: "%.4f", serverCost))")
                // Show upgrade prompt if over threshold but don't block chat. Never for
                // paid/BYOK users — they aren't subject to the free Omi spend cap.
                if self.isUsingOmiAccountProvider && serverCost >= 50.0
                    && !self.isExemptFromOmiUpgradeNudge {
                    log("ChatProvider: Omi AI cost at $\(String(format: "%.2f", serverCost)) on startup — showing upgrade prompt")
                    self.showOmiThresholdAlert = true
                }
            }
        }

        if multiChatEnabled {
            // Multi-chat mode: load sessions, default to default chat
            await fetchSessions()
            // Start in default chat mode
            await switchToDefaultChat()
        } else {
            // Single chat mode: just load default chat messages (syncs with Flutter)
            isLoadingSessions = false
            await loadDefaultChatMessages()
        }
    }

    /// Warm local prompt context used by first send / bridge startup.
    func warmupPromptContext() async {
        await refreshMemoriesForPrompt()
        await loadGoalsIfNeeded()
        await loadTasksIfNeeded()
        await loadAIProfileIfNeeded()
        await loadSchemaIfNeeded()
        await discoverClaudeConfig()

        // Set working directory for Claude Agent SDK if workspace is configured
        if workingDirectory == nil, !aiChatWorkingDirectory.isEmpty {
            workingDirectory = aiChatWorkingDirectory
        }
    }

    private func effectiveAgentWorkingDirectory() -> String {
        if let workingDirectory, !workingDirectory.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return workingDirectory
        }
        let artifactsDirectory = AgentRuntimeProcess.defaultArtifactsDirectory()
        try? FileManager.default.createDirectory(
            at: URL(fileURLWithPath: artifactsDirectory),
            withIntermediateDirectories: true
        )
        return artifactsDirectory
    }

    /// Reinitialize after settings change
    func reinitialize() async {
        sessions = []
        messages = []
        resetMessagesPagination()
        currentSession = nil
        isInDefaultChat = true
        await initialize()
    }

    /// Retry loading after a failure — clears error state and re-runs initialize
    func retryLoad() async {
        sessionsLoadError = nil
        await initialize()
    }

    // MARK: - CLAUDE.md & Skills Discovery

    /// Results from background Claude config discovery
    private struct ClaudeConfigResult: Sendable {
        let claudeMdContent: String?
        let claudeMdPath: String?
        let skills: [(name: String, description: String, path: String)]
        let projectClaudeMdContent: String?
        let projectClaudeMdPath: String?
        let projectSkills: [(name: String, description: String, path: String)]
        let devModeContext: String?
    }

    /// Perform all file I/O for Claude config discovery off the main thread
    private nonisolated static func loadClaudeConfigFromDisk(workspace: String) -> ClaudeConfigResult {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let claudeDir = "\(home)/.claude"
        let fm = FileManager.default

        // Discover global CLAUDE.md
        let mdPath = "\(claudeDir)/CLAUDE.md"
        var globalMdContent: String?
        var globalMdPath: String?
        if fm.fileExists(atPath: mdPath),
           let content = try? String(contentsOfFile: mdPath, encoding: .utf8) {
            globalMdContent = content
            globalMdPath = mdPath
        }

        // Discover global skills
        var skills: [(name: String, description: String, path: String)] = []
        let skillsDir = "\(claudeDir)/skills"
        if let skillDirs = try? fm.contentsOfDirectory(atPath: skillsDir) {
            for dir in skillDirs.sorted() {
                let skillPath = "\(skillsDir)/\(dir)/SKILL.md"
                if fm.fileExists(atPath: skillPath),
                   let content = try? String(contentsOfFile: skillPath, encoding: .utf8) {
                    let desc = extractSkillDescription(from: content)
                    skills.append((name: dir, description: desc, path: skillPath))
                }
            }
        }

        // Discover project-level config from workspace directory
        var projMdContent: String?
        var projMdPath: String?
        var projectSkills: [(name: String, description: String, path: String)] = []

        if !workspace.isEmpty, fm.fileExists(atPath: workspace) {
            let projectMdPath = "\(workspace)/CLAUDE.md"
            if fm.fileExists(atPath: projectMdPath),
               let content = try? String(contentsOfFile: projectMdPath, encoding: .utf8) {
                projMdContent = content
                projMdPath = projectMdPath
            }

            let projectSkillsDir = "\(workspace)/.claude/skills"
            if let skillDirs = try? fm.contentsOfDirectory(atPath: projectSkillsDir) {
                for dir in skillDirs.sorted() {
                    let skillPath = "\(projectSkillsDir)/\(dir)/SKILL.md"
                    if fm.fileExists(atPath: skillPath),
                       let content = try? String(contentsOfFile: skillPath, encoding: .utf8) {
                        let desc = extractSkillDescription(from: content)
                        projectSkills.append((name: dir, description: desc, path: skillPath))
                    }
                }
            }
        }

        // Load dev-mode skill content (full SKILL.md, not just description)
        var devMode: String?
        let devModeSkillPath = "\(skillsDir)/dev-mode/SKILL.md"
        if fm.fileExists(atPath: devModeSkillPath),
           let content = try? String(contentsOfFile: devModeSkillPath, encoding: .utf8) {
            var body = content
            if body.hasPrefix("---") {
                let lines = body.components(separatedBy: "\n")
                if let endIdx = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("---") }) {
                    body = lines[(endIdx + 1)...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
                }
            }
            devMode = body
        } else {
            let projectDevModePath = "\(workspace)/.claude/skills/dev-mode/SKILL.md"
            if !workspace.isEmpty, fm.fileExists(atPath: projectDevModePath),
               let content = try? String(contentsOfFile: projectDevModePath, encoding: .utf8) {
                var body = content
                if body.hasPrefix("---") {
                    let lines = body.components(separatedBy: "\n")
                    if let endIdx = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("---") }) {
                        body = lines[(endIdx + 1)...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
                    }
                }
                devMode = body
            }
        }

        return ClaudeConfigResult(
            claudeMdContent: globalMdContent,
            claudeMdPath: globalMdPath,
            skills: skills,
            projectClaudeMdContent: projMdContent,
            projectClaudeMdPath: projMdPath,
            projectSkills: projectSkills,
            devModeContext: devMode
        )
    }

    /// Discover ~/.claude/CLAUDE.md, skills from ~/.claude/skills/, and project-level equivalents
    func discoverClaudeConfig() async {
        let workspace = aiChatWorkingDirectory
        let result = await Task.detached(priority: .utility) {
            Self.loadClaudeConfigFromDisk(workspace: workspace)
        }.value

        // Assign results back on main actor
        claudeMdContent = result.claudeMdContent
        claudeMdPath = result.claudeMdPath
        discoveredSkills = result.skills
        projectClaudeMdContent = result.projectClaudeMdContent
        projectClaudeMdPath = result.projectClaudeMdPath
        projectDiscoveredSkills = result.projectSkills
        devModeContext = result.devModeContext

        log("ChatProvider: discovered global CLAUDE.md=\(claudeMdContent != nil), global skills=\(discoveredSkills.count), project CLAUDE.md=\(projectClaudeMdContent != nil), project skills=\(projectDiscoveredSkills.count), dev_mode_skill=\(devModeContext != nil)")
    }

    /// Extract description from YAML frontmatter in SKILL.md
    nonisolated static func extractSkillDescription(from content: String) -> String {
        guard content.hasPrefix("---") else {
            // No frontmatter — use first non-empty line as description
            let lines = content.components(separatedBy: "\n")
            return lines.first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty })?.trimmingCharacters(in: .whitespaces) ?? ""
        }
        let lines = content.components(separatedBy: "\n")
        for line in lines.dropFirst() {
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("---") { break }
            if line.trimmingCharacters(in: .whitespaces).hasPrefix("description:") {
                var value = String(line.trimmingCharacters(in: .whitespaces).dropFirst("description:".count))
                value = value.trimmingCharacters(in: .whitespaces)
                // Remove surrounding quotes if present
                if (value.hasPrefix("\"") && value.hasSuffix("\"")) ||
                   (value.hasPrefix("'") && value.hasSuffix("'")) {
                    value = String(value.dropFirst().dropLast())
                }
                return value
            }
        }
        return ""
    }

    /// Get the set of enabled skill names (all skills minus explicitly disabled ones)
    func getEnabledSkillNames() -> Set<String> {
        let allSkillNames = Set(discoveredSkills.map { $0.name } + projectDiscoveredSkills.map { $0.name })
        let disabled = getDisabledSkillNames()
        return allSkillNames.subtracting(disabled)
    }

    /// Get the set of explicitly disabled skill names from UserDefaults
    func getDisabledSkillNames() -> Set<String> {
        guard let data = disabledSkillsJSON.data(using: .utf8),
              let names = try? JSONDecoder().decode([String].self, from: data) else {
            return [] // Default: nothing disabled = all enabled
        }
        return Set(names)
    }

    /// Save the set of disabled skill names to UserDefaults
    func setDisabledSkillNames(_ names: Set<String>) {
        if let data = try? JSONEncoder().encode(Array(names)),
           let json = String(data: data, encoding: .utf8) {
            disabledSkillsJSON = json
        }
    }

    /// Switch to the default chat (messages without session_id, syncs with Flutter app)
    func switchToDefaultChat() async {
        currentSession = nil
        isInDefaultChat = true
        await loadDefaultChatMessages()
        log("Switched to default chat")
    }

    /// Load messages for the default chat (no session filter - compatible with Flutter)
    /// Retries up to 3 times on failure.
    func loadDefaultChatMessages() async {
        isLoading = true
        errorMessage = nil
        hasMoreMessages = false

        let maxAttempts = 3
        let delays: [UInt64] = [1_000_000_000, 2_000_000_000] // 1s, 2s
        var lastError: Error?

        for attempt in 1...maxAttempts {
            do {
                let persistedMessages = try await APIClient.shared.getMessages(
                    appId: selectedAppId,
                    limit: messagesPageSize
                )
                messages = persistedMessages.map(ChatMessage.init(from:))
                    .sorted(by: { $0.createdAt < $1.createdAt })
                await rehydrateMissingArtifactResourcesFromKernel()
                messagesPaginationOffset = persistedMessages.count
                hasMoreMessages = persistedMessages.count == messagesPageSize
                sessionsLoadError = nil
                log("ChatProvider loaded \(messages.count) default chat messages, hasMore: \(hasMoreMessages)")
                isLoading = false
                return
            } catch {
                lastError = error
                logError("Failed to load default chat messages (attempt \(attempt)/\(maxAttempts))", error: error)
                if attempt < maxAttempts {
                    try? await Task.sleep(nanoseconds: delays[attempt - 1])
                }
            }
        }

        messages = []
        resetMessagesPagination()
        sessionsLoadError = lastError?.localizedDescription ?? "Failed to load messages. Check your connection and try again."
        isLoading = false
    }

    // MARK: - Cross-Platform Message Sync

    /// Prevents overlapping fetches when activation + Cmd+R fire back-to-back.
    private let pollGate = ReentrancyGate()

    /// Defense-in-depth against the saveMessage / pollForNewMessages
    /// race. `isSending` is released *before* the AI message save
    /// completes (intentional — to unblock the next query), which opens a
    /// window where the poll can observe the just-saved AI message and
    /// treat it as new-from-another-platform. The existing 200-char
    /// text-prefix merge at `pollForNewMessages` catches most of these,
    /// but a counter-based suppression eliminates the race window
    /// entirely instead of relying on text heuristics that fail on short
    /// common replies ("Yes", "Got it"). Every saveMessage call site
    /// begins/ends the counter; the poll skips when the counter is
    /// active. Sites are documented inline at each `saveMessage(...)` call.
    private let pendingSaves = PendingSaveCounter()

    /// Set when a `pollForNewMessages` cycle bailed *because* a save was
    /// in flight. `pollForNewMessages` is only triggered by activation /
    /// Cmd+R (there is no periodic poll), so a dropped cycle would leave
    /// messages from other platforms unfetched until the next activation.
    /// `pendingSaves.onDrained` re-runs the poll once saves finish, but
    /// only when this flag says one was actually deferred.
    private var pollDeferredDuringSave = false

    /// Fetch new messages from other platforms (e.g. mobile).
    /// Merges new messages into the existing array without disrupting the UI.
    private func pollForNewMessages() async {
        // Prevent overlapping fetches from activation + Cmd+R firing together
        guard pollGate.tryEnter() else { return }
        defer { pollGate.exit() }
        // Skip if user is signed out (tokens are cleared)
        guard AuthState.shared.isSignedIn else { return }
        // Skip if in auth backoff period (recent 401 errors)
        guard !AuthBackoffTracker.shared.shouldSkipRequest() else { return }
        // Skip if we're actively sending. Note: isSending is released *before* the AI
        // message is saved to the backend (to unblock the next query). This means the
        // poll can run while saveMessage() is still in-flight — see the race note below.
        //
        // `pendingSaves.isActive` closes the same race window from the save side
        // — any in-flight saveMessage (user msg, AI msg, follow-up, partial-on-error,
        // proactive notification) keeps the poll suppressed until it lands. This is
        // defense-in-depth over the 200-char text-prefix merge below at lines ~2192.
        guard !isSending, !isLoading, !isLoadingSessions else { return }
        // A save in flight means a local message hasn't reconciled its
        // server ID yet — defer rather than risk observing it as new.
        // Mark the cycle deferred so `pendingSaves.onDrained` re-runs it.
        guard !pendingSaves.isActive else { pollDeferredDuringSave = true; return }
        // Skip if messages haven't been loaded yet (initial load not done)
        guard !messages.isEmpty || sessionsLoadError != nil else { return }
        // Skip if there's an active streaming message
        guard !messages.contains(where: { $0.isStreaming }) else { return }

        // Past all the deferral-relevant guards — this cycle is actually
        // going to fetch, so any pending deferral is now being honored.
        // Cleared HERE (not in onDrained) so a retry that bailed earlier
        // on `isSending`/streaming keeps the flag set and gets retried by
        // the next drain. The post-fetch recheck below re-sets it if a
        // save sneaks in during getMessages.
        pollDeferredDuringSave = false

        do {
            let persistedMessages: [ChatMessageDB]

            if let session = currentSession {
                // Multi-chat: fetch for current session
                persistedMessages = try await APIClient.shared.getMessages(
                    sessionId: session.id,
                    limit: messagesPageSize
                )
            } else {
                // Default chat
                persistedMessages = try await APIClient.shared.getMessages(
                    appId: selectedAppId,
                    limit: messagesPageSize
                )
            }

            // A save may have begun *while* getMessages was awaiting — e.g.
            // a proactive assistant message appended via appendAssistantMessage
            // (FloatingControlBarWindow) after this poll already passed the
            // pendingSaves guard above. That message can be in the batch we
            // just fetched, carrying a server ID the local copy hasn't adopted
            // yet. Re-check here and bail this cycle; the next poll after the
            // save lands reconciles it by ID. Without this, the post-guard
            // window stays open for the proactive paths. Mark the cycle
            // deferred so the drain handler re-runs it — otherwise the
            // just-fetched batch (including any genuine new messages from
            // other platforms) would be dropped until the next activation.
            guard !pendingSaves.isActive else { pollDeferredDuringSave = true; return }

            // Build a lookup of existing IDs for fast O(1) checks.
            let existingIds = Set(messages.map(\.id))

            var genuinelyNewMessages: [ChatMessage] = []

            for dbMsg in persistedMessages {
                // Fast path: already in memory by server ID — skip.
                if existingIds.contains(dbMsg.id) { continue }

                // Race-condition guard: isSending is released before the backend save
                // completes (intentionally, to unblock the next query). If this poll
                // fires between "isSending = false" and "messages[i].id = response.id",
                // the backend message lands here with a server ID that doesn't match
                // the local UUID still sitting in messages[]. Without this check we'd
                // append a duplicate.
                //
                // Detection: find an in-memory message that (a) hasn't been synced yet
                // (isSynced=false → still has a local UUID) and (b) has the same text.
                // If found, this is the same message — just update its ID in-place
                // instead of appending a copy.
                let dbSender: ChatSender = dbMsg.sender == "human" ? .user : .ai
                let dbPrefix = String(dbMsg.text.prefix(200))
                if let localIndex = messages.firstIndex(where: {
                    !$0.isSynced && $0.sender == dbSender && String($0.text.prefix(200)) == dbPrefix
                }) {
                    // Merge: adopt the server ID so future polls find it by ID.
                    messages[localIndex].id = dbMsg.id
                    messages[localIndex].isSynced = true
                    if messages[localIndex].resources.isEmpty {
                        let resources = ChatResource.decodeResourcesFromMessageMetadata(dbMsg.metadata)
                        if !resources.isEmpty {
                            messages[localIndex].resources = resources
                        }
                    }
                    log("ChatProvider poll: merged backend ID \(dbMsg.id) into local message (was unsynced)")
                    continue
                }

                // Genuinely new message from another platform (phone, web, etc.)
                genuinelyNewMessages.append(ChatMessage(from: dbMsg))
            }

            if !genuinelyNewMessages.isEmpty {
                log("ChatProvider poll: found \(genuinelyNewMessages.count) new message(s) from other platforms")
                messages.append(contentsOf: genuinelyNewMessages)
                messages.sort(by: { $0.createdAt < $1.createdAt })
            }
            AuthBackoffTracker.shared.reportSuccess()
        } catch {
            if case APIError.unauthorized = error {
                AuthBackoffTracker.shared.reportAuthFailure()
            }
            // Benign sign-out race: the isSignedIn guard above passed, but the
            // token was cleared by the time getMessages ran. Expected, not a bug
            // — log quietly (breadcrumb only) instead of flooding Sentry.
            if case AuthError.notSignedIn = error {
                log("ChatProvider poll skipped: signed out mid-cycle")
                return
            }
            // Silent failure — polling errors shouldn't disrupt the user
            logError("ChatProvider poll failed", error: error)
        }
    }

    // MARK: - Stop / Follow-Up

    private struct PendingFollowUpRequest {
        let text: String
        let model: String?
        let systemPromptSuffix: String?
        let systemPromptPrefix: String?
        let systemPromptStyle: ChatSystemPromptStyle
        let surfaceRef: AgentSurfaceReference?
        let turnOwner: ChatTurnOwner
    }

    /// Follow-ups queued while the current query is being interrupted.
    /// Drained FIFO at the end of `sendMessage` so rapid barge-ins do not overwrite each other.
    private var pendingFollowUps: [PendingFollowUpRequest] = []
    private var activeFollowUpContext: PendingFollowUpRequest?

    /// Stop the running agent, keeping partial response
    func canInterruptActiveTurn(owner: ChatTurnOwner) -> Bool {
        guard isSending else { return true }
        guard let activeTurnOwner else { return false }
        return owner.canInterrupt(activeTurnOwner)
    }

    @discardableResult
    func stopAgent(owner: ChatTurnOwner) -> Bool {
        guard isSending else { return false }
        guard let activeTurnOwner, owner.canInterrupt(activeTurnOwner) else {
            log("ChatProvider: ignoring stop from non-owner turn")
            return false
        }
        isStopping = true
        let stoppedGen = sendGeneration
        sendGeneration += 1
        let myGen = sendGeneration
        Task {
            let shouldInterruptBridge = await MainActor.run { () -> Bool in
                guard self.isSending,
                      self.sendGeneration == myGen,
                      self.activeBridgeSendGeneration == stoppedGen else {
                    return false
                }
                self.activeBridgeSendGeneration = nil
                return true
            }
            if shouldInterruptBridge {
                await resolvedAgentClient().interrupt()
            }
            // Normal path: interrupt → bridge emits final result or .stopped.
            // Fallback: if the bridge drops the turn_end as "stray", force-release
            // after a short grace so the user's next query is not silently swallowed.
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            await MainActor.run {
                if self.isSending && self.sendGeneration == myGen {
                    log("ChatProvider: interrupt didn't close stream in 3s — force-resetting isSending")
                    self.releaseSendLock(sendGeneration: myGen)
                }
            }
        }
        // Result flows back normally through the bridge with partial text
        return true
    }

    /// Send a follow-up message while the agent is still running.
    /// Interrupts the current query and chains a new one with full context.
    func sendFollowUp(_ text: String) async {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty, isSending else { return }

        // Add as user message in UI
        let userMessage = ChatMessage(
            id: UUID().uuidString,
            text: trimmedText,
            sender: .user
        )
        messages.append(userMessage)
        // Signal local send for turn anchoring.
        localSendToken = LocalSendToken(generation: localSendToken.generation + 1)

        // Persist to backend and sync server ID back to prevent poll duplicates.
        //
        // saveMessage site 1 of 5: user follow-up message sent
        // mid-query. Fire-and-forget Task. `pendingSaves` guards the
        // poll for the lifetime of this save.
        let capturedSessionId = isInDefaultChat ? nil : currentSessionId
        let capturedAppId = overrideAppId ?? selectedAppId
        let localId = userMessage.id
        pendingSaves.begin()
        Task { [weak self] in
            do {
                let response = try await APIClient.shared.saveMessage(
                    text: trimmedText,
                    sender: "human",
                    appId: capturedAppId,
                    sessionId: capturedSessionId,
                    clientMessageId: localId
                )
                await MainActor.run {
                    if let index = self?.messages.firstIndex(where: { $0.id == localId }) {
                        self?.messages[index].id = response.id
                        self?.messages[index].isSynced = true
                    }
                    self?.pendingSaves.end()
                }
                log("Saved follow-up message to backend: \(response.id)")
            } catch {
                await MainActor.run { self?.pendingSaves.end() }
                logError("Failed to persist follow-up message", error: error)
            }
        }

        // Queue the follow-up and interrupt the current query.
        // When sendMessage finishes (due to the interrupt), it checks
        // pendingFollowUps and chains a new full query automatically.
        let context = activeFollowUpContext ?? PendingFollowUpRequest(
            text: trimmedText,
            model: nil,
            systemPromptSuffix: nil,
            systemPromptPrefix: nil,
            systemPromptStyle: .main,
            surfaceRef: nil,
            turnOwner: activeTurnOwner ?? .mainChat
        )
        pendingFollowUps.append(PendingFollowUpRequest(
            text: trimmedText,
            model: context.model,
            systemPromptSuffix: context.systemPromptSuffix,
            systemPromptPrefix: context.systemPromptPrefix,
            systemPromptStyle: context.systemPromptStyle,
            surfaceRef: context.surfaceRef,
            turnOwner: context.turnOwner
        ))
        await resolvedAgentClient().interrupt()
        log("ChatProvider: follow-up queued, interrupt sent")
    }

    @discardableResult
    func appendAssistantMessage(
        _ text: String,
        clientTurnId: String? = nil,
        notificationContext: String? = nil,
        notificationScreenshot: Data? = nil,
        resources: [ChatResource] = []
    ) -> ChatMessage? {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty || !resources.isEmpty else { return nil }

        let messageText = trimmedText.isEmpty ? "Done." : trimmedText
        let aiMessage = ChatMessage(
            clientTurnId: clientTurnId,
            text: messageText,
            sender: .ai,
            notificationContext: notificationContext,
            notificationScreenshot: notificationScreenshot,
            resources: resources
        )
        let localId = aiMessage.id
        let capturedSessionId = isInDefaultChat ? nil : currentSessionId
        let capturedAppId = overrideAppId ?? selectedAppId

        messages.append(aiMessage)

        // saveMessage site 2 of 5: AI message synthesized from a
        // proactive notification (no bridge query, no streaming).
        // Fire-and-forget Task.
        let capturedResources = resources
        let capturedMetadata = ChatResource.mergeResourcesIntoMessageMetadata(nil, resources: capturedResources)
        pendingSaves.begin()
        Task { [weak self] in
            do {
                let response = try await APIClient.shared.saveMessage(
                    text: messageText,
                    sender: "ai",
                    appId: capturedAppId,
                    sessionId: capturedSessionId,
                    metadata: capturedMetadata,
                    clientMessageId: localId
                )
                await MainActor.run {
                    if let index = self?.messages.firstIndex(where: { $0.id == localId }) {
                        self?.messages[index].id = response.id
                        self?.messages[index].isSynced = true
                    }
                    self?.pendingSaves.end()
                }
                log("Saved assistant message to backend: \(response.id)")
            } catch {
                await MainActor.run { self?.pendingSaves.end() }
                logError("Failed to persist assistant message", error: error)
            }
        }

        return aiMessage
    }

    /// Record a completed turn that did not stream through `sendMessage`.
    /// Appends both messages to the in-memory provider session immediately, then
    /// persists them sequentially in the background so later follow-ups retain context.
    @discardableResult
    func recordCompletedTurn(
        userText: String,
        assistantText: String,
        logLabel: String = "completed",
        messageSource: String = "desktop_chat"
    ) -> (
        user: ChatMessage?, assistant: ChatMessage?
    ) {
        let user = userText.trimmingCharacters(in: .whitespacesAndNewlines)
        let assistant = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !user.isEmpty || !assistant.isEmpty else {
            return (nil, nil)
        }

        let capturedSessionId = isInDefaultChat ? nil : currentSessionId
        let capturedAppId = overrideAppId ?? selectedAppId

        var userMessage: ChatMessage?
        var aiMessage: ChatMessage?
        if !user.isEmpty {
            let m = ChatMessage(text: user, sender: .user)
            messages.append(m)
            userMessage = m
        }
        if !assistant.isEmpty {
            let m = ChatMessage(text: assistant, sender: .ai)
            messages.append(m)
            aiMessage = m
        }

        pendingSaves.begin()
        Task { [weak self] in
            if let userMessage {
                await self?.persistRecordedTurnMessage(
                    userMessage, text: user, sender: "human",
                    appId: capturedAppId, sessionId: capturedSessionId, logLabel: logLabel, messageSource: messageSource)
            }
            if let aiMessage {
                await self?.persistRecordedTurnMessage(
                    aiMessage, text: assistant, sender: "ai",
                    appId: capturedAppId, sessionId: capturedSessionId, logLabel: logLabel, messageSource: messageSource)
            }
            await MainActor.run { self?.pendingSaves.end() }
        }

        return (userMessage, aiMessage)
    }

    func mainChatSurfaceReference() -> AgentSurfaceReference {
        .mainChat(chatId: mainChatRuntimeChatId(sessionId: isInDefaultChat ? nil : currentSessionId))
    }

    /// Persist one recorded-turn message and sync its server ID back into `messages` so a
    /// subsequent poll doesn't duplicate it. Failures leave the in-memory copy unsynced
    /// (matches the existing saveMessage sites — no retry).
    private func persistRecordedTurnMessage(
        _ message: ChatMessage,
        text: String,
        sender: String,
        appId: String?,
        sessionId: String?,
        logLabel: String,
        messageSource: String
    ) async {
        do {
            let metadata = ChatResource.mergeResourcesIntoMessageMetadata(nil, resources: message.resources)
            let response = try await APIClient.shared.saveMessage(
                text: text,
                sender: sender,
                appId: appId,
                sessionId: sessionId,
                metadata: metadata,
                clientMessageId: message.id,
                messageSource: messageSource
            )
            await MainActor.run {
                if let index = self.messages.firstIndex(where: { $0.id == message.id }) {
                    self.messages[index].id = response.id
                    self.messages[index].isSynced = true
                }
            }
            log("Saved \(logLabel) \(sender) message to backend: \(response.id)")
        } catch {
            logError("Failed to persist \(logLabel) \(sender) message", error: error)
        }
    }

    // MARK: - Pending Attachments

    /// Stage attachments for the next message and kick off background upload.
    /// Caps the total at `kMaxChatAttachments` (matches Flutter's 4-file limit).
    func addAttachments(_ attachments: [ChatAttachment]) {
        let room = max(0, kMaxChatAttachments - pendingAttachments.count)
        guard room > 0 else {
            errorMessage = "You can only attach up to \(kMaxChatAttachments) files."
            return
        }
        let toAdd = Array(attachments.prefix(room))
        pendingAttachments.append(contentsOf: toAdd)
        let capturedAppId = overrideAppId ?? selectedAppId
        for attachment in toAdd {
            uploadAttachment(id: attachment.id, appId: capturedAppId)
        }
    }

    func removePendingAttachment(id: String) {
        pendingAttachments.removeAll { $0.id == id }
    }

    /// Upload a single staged attachment in the background. The user can send
    /// the message before this completes — `sendMessage` will await the upload.
    private func uploadAttachment(id: String, appId: String?) {
        Task { [weak self] in
            guard let self = self,
                  let attachment = await MainActor.run(body: {
                      self.pendingAttachments.first(where: { $0.id == id })
                  })
            else { return }

            // For non-image files we still need bytes — load them lazily here
            // (we skipped this at add-time to keep the UI responsive).
            let data: Data? = attachment.data
                ?? attachment.localFileURL.flatMap { try? Data(contentsOf: $0) }
            guard let bytes = data else {
                await MainActor.run {
                    if attachment.isSendableLocalResource {
                        self.setAttachmentState(id: id, state: .localOnly)
                    } else {
                        self.setAttachmentState(id: id, state: .failed("File could not be read"))
                    }
                }
                return
            }
            do {
                let resp = try await APIClient.shared.uploadChatFiles(
                    [(data: bytes, fileName: attachment.fileName, mimeType: attachment.mimeType)],
                    appId: appId
                )
                guard let server = resp.first else {
                    throw APIError.invalidResponse
                }
                await MainActor.run {
                    if let idx = self.pendingAttachments.firstIndex(where: { $0.id == id }) {
                        self.pendingAttachments[idx].serverId = server.id
                        self.pendingAttachments[idx].thumbnailURL = server.thumbnail
                        if let mime = server.mimeType { self.pendingAttachments[idx].mimeType = mime }
                        if let name = server.name { self.pendingAttachments[idx].fileName = name }
                        self.pendingAttachments[idx].state = .uploaded
                    }
                }
            } catch {
                logError("ChatProvider: attachment upload failed", error: error)
                await MainActor.run {
                    if attachment.isSendableLocalResource {
                        self.setAttachmentState(id: id, state: .localOnly)
                    } else {
                        self.setAttachmentState(id: id, state: .failed(error.localizedDescription))
                    }
                }
            }
        }
    }

    private func setAttachmentState(id: String, state: ChatAttachment.State) {
        guard let idx = pendingAttachments.firstIndex(where: { $0.id == id }) else { return }
        pendingAttachments[idx].state = state
    }

    /// Serialize attachments to the JSON string stored in `metadata` on the
    /// backend. Only the fields needed to re-render thumbnails are kept; image
    /// bytes never travel through this channel.
    private func encodeAttachmentsMetadata(_ attachments: [ChatAttachment]) -> String? {
        let items: [[String: Any]] = attachments.map { att in
            var dict: [String: Any] = [
                "id": att.serverId ?? att.id,
                "name": att.fileName,
                "mime_type": att.mimeType,
            ]
            if let thumb = att.thumbnailURL { dict["thumbnail"] = thumb }
            return dict
        }
        let root: [String: Any] = ["attachments": items]
        guard let data = try? JSONSerialization.data(withJSONObject: root),
              let str = String(data: data, encoding: .utf8)
        else { return nil }
        return str
    }

    /// Block until all currently-uploading attachments either succeed or fail.
    /// Returns `false` if any failed — caller surfaces an error and aborts.
    private func awaitPendingUploads() async -> Bool {
        let timeoutNs: UInt64 = 60 * 1_000_000_000  // 60s safety bound
        let start = DispatchTime.now().uptimeNanoseconds
        while pendingAttachments.contains(where: {
            if case .uploading = $0.state { return true }
            return false
        }) {
            if DispatchTime.now().uptimeNanoseconds - start > timeoutNs {
                errorMessage = "Attachment upload timed out."
                return false
            }
            try? await Task.sleep(nanoseconds: 100_000_000)
        }
        return !pendingAttachments.contains(where: {
            if case .failed = $0.state { return !$0.isSendableLocalResource }
            return false
        })
    }

    nonisolated static func attachmentContextPrompt(for attachments: [ChatAttachment]) -> String? {
        guard !attachments.isEmpty else { return nil }
        let plural = attachments.count == 1 ? "file" : "files"
        var lines: [String] = [
            "[Attached Files]",
            "The user attached \(attachments.count) \(plural) to this exact message. Treat references like \"this\", \"the file\", \"the attachment\", or \"what do you think of this\" as referring to these attachment(s). If the answer depends on file contents, inspect the local_path with file-reading tools before asking for clarification.",
        ]
        for (index, attachment) in attachments.enumerated() {
            lines.append("")
            lines.append("\(index + 1). \(attachment.fileName)")
            lines.append("   mime_type: \(attachment.mimeType)")
            if let localFileURL = attachment.localFileURL {
                lines.append("   local_path: \(localFileURL.path)")
                if let attrs = try? FileManager.default.attributesOfItem(atPath: localFileURL.path),
                   let size = attrs[.size] as? NSNumber {
                    lines.append(
                        "   size: \(ByteCountFormatter.string(fromByteCount: size.int64Value, countStyle: .file))"
                    )
                }
            } else {
                lines.append("   local_path: unavailable")
            }
            if let serverId = attachment.serverId {
                lines.append("   uploaded_file_id: \(serverId)")
            }
            if attachment.isImage {
                lines.append("   image_payload: included separately when available")
            }
        }
        return lines.joined(separator: "\n")
    }

    // MARK: - Send Message

    /// Send a message and get AI response via Claude Agent SDK bridge
    /// Persists both user and AI messages to backend
    /// - Parameters:
    ///   - text: The message text
    ///   - model: Optional model override for this query (e.g. "claude-sonnet-4-6" for floating bar)
    @discardableResult
    func sendMessage(
        _ text: String,
        model: String? = nil,
        isFollowUp: Bool = false,
        systemPromptSuffix: String? = nil,
        systemPromptPrefix: String? = nil,
        systemPromptStyle: ChatSystemPromptStyle = .main,
        surfaceRef: AgentSurfaceReference? = nil,
        imageData: Data? = nil,
        turnOwner: ChatTurnOwner = .mainChat,
        clientTurnId: String = UUID().uuidString
    ) async -> String? {
        let trimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedText.isEmpty else { return nil }

        // Guard against concurrent sendMessage calls.
        // The bridge uses a single message continuation, so concurrent queries
        // would cause responses to be consumed by the wrong caller.
        guard !isSending else {
            log("ChatProvider: sendMessage called while already sending, ignoring")
            return nil
        }

        // Monthly free-tier limit shared with the floating bar (30 messages/month).
        // Block the send, surface the popup, and let the user upgrade.
        let usageLimiter = FloatingBarUsageLimiter.shared
        if isUsingOmiAccountProvider {
            if usageLimiter.isLimitReached {
                log("ChatProvider: sendMessage blocked — free-tier monthly chat limit reached")
                errorMessage = "You've reached \(usageLimiter.limitDescription). Upgrade to keep chatting."
                NotificationCenter.default.post(
                    name: .showUsageLimitPopup,
                    object: nil,
                    userInfo: ["reason": "chat"]
                )
                return nil
            }
        }

        // QueryTracer: picked up from the TaskLocal context established by the
        // floating-bar / PTT entry points (nil for non-traced call sites).
        let tracer = QueryTracerContext.current

        isSending = true
        isStopping = false
        activeTurnOwner = turnOwner
        errorMessage = nil
        currentError = nil
        sendGeneration += 1
        let sendGen = sendGeneration
        activeFollowUpContext = PendingFollowUpRequest(
            text: trimmedText,
            model: model,
            systemPromptSuffix: systemPromptSuffix,
            systemPromptPrefix: systemPromptPrefix,
            systemPromptStyle: systemPromptStyle,
            surfaceRef: surfaceRef,
            turnOwner: turnOwner
        )

        // Ensure bridge is running
        tracer?.begin("bridge_ensure")
        guard await ensureBridgeStarted() else {
            tracer?.end("bridge_ensure", metadata: ["error": "bridge_failed"])
            tracer?.finalize(tokenCount: 0, model: model ?? modelOverride)
            if errorMessage?.isEmpty ?? true {
                errorMessage = "AI not available"
            }
            releaseSendLock(sendGeneration: sendGen)
            return nil
        }
        tracer?.end("bridge_ensure", metadata: ["status": "ok"])
        guard sendGeneration == sendGen else {
            tracer?.finalize(tokenCount: 0, model: model ?? modelOverride)
            clearSendLockState()
            return nil
        }

        // Show upgrade prompt if over threshold but don't block the message.
        // Never for paid/BYOK users — they aren't subject to the free Omi spend cap.
        if isUsingOmiAccountProvider && omiAICumulativeCostUsd >= 50.0
            && !isExemptFromOmiUpgradeNudge {
            showOmiThresholdAlert = true
        }

        // Determine session ID based on mode
        // In default chat mode (isInDefaultChat=true): no session ID (compatible with Flutter)
        // In session mode: require session ID
        var sessionId: String? = nil
        if !isInDefaultChat {
            // Session mode - require a session
            if currentSession == nil {
                _ = await createNewSession()
            }
            guard let sid = currentSessionId else {
                errorMessage = "Failed to create chat session"
                tracer?.finalize(tokenCount: 0, model: model ?? modelOverride)
                releaseSendLock(sendGeneration: sendGen)
                return nil
            }
            sessionId = sid
        }
        guard sendGeneration == sendGen else {
            tracer?.finalize(tokenCount: 0, model: model ?? modelOverride)
            clearSendLockState()
            return nil
        }

        // Safety-net watchdog: if this specific send is still "in flight"
        // 3 minutes from now, something in the bridge / stream pipeline has
        // hung (commonly: stale ACP subprocess after laptop sleep emits a
        // "stray turn_end" that Swift's waitForMessage never sees). Force-
        // release isSending so the user's next query isn't silently dropped
        // by the "already sending" guard. The generation check means the
        // watchdog only fires if no later send has replaced this one.
        Task { [weak self] in
            do {
                try await Task.sleep(nanoseconds: 180_000_000_000)
            } catch {
                return
            }
            guard let self else { return }
            let stillStuck = await MainActor.run { () -> Bool in
                guard self.isSending, self.sendGeneration == sendGen else { return false }
                log("ChatProvider: send watchdog fired at 180s — bridge is stuck; force-resetting")
                return true
            }
            guard stillStuck else { return }
            await self.resolvedAgentClient().interrupt()
            await MainActor.run {
                guard self.isSending, self.sendGeneration == sendGen else { return }
                _ = self.releaseSendLock(sendGeneration: sendGen)
                self.errorMessage = "Response took too long. Try again."
            }
        }

        // Wait for staged attachments to finish uploading so we can include their
        // server IDs in the saved-message metadata. The bubble shows immediately
        // via the local thumbnail data — we only block sending until the upload
        // settles so persistence stays consistent across sessions.
        var attachmentsForMessage: [ChatAttachment] = []
        if !pendingAttachments.isEmpty {
            let ok = await awaitPendingUploads()
            guard sendGeneration == sendGen else {
                tracer?.finalize(tokenCount: 0, model: model ?? modelOverride)
                clearSendLockState()
                return nil
            }
            if !ok {
                releaseSendLock(sendGeneration: sendGen)
                errorMessage = "Some attachments failed to upload. Remove them and try again."
                tracer?.finalize(tokenCount: 0, model: model ?? modelOverride)
                return nil
            }
            attachmentsForMessage = pendingAttachments
            pendingAttachments.removeAll()
        }
        let attachmentMetadataJSON = attachmentsForMessage.isEmpty
            ? nil
            : encodeAttachmentsMetadata(attachmentsForMessage)

        if isUsingOmiAccountProvider {
            usageLimiter.recordQuery()
        }

        // Save user message to backend and add to UI.
        // (skip for follow-ups — sendFollowUp already did both)
        //
        // The save is fire-and-forget (unstructured Task) so it doesn't block
        // the ACP query from starting. This is safe because isSending=true for
        // the entire duration of the ACP query, so the poll timer is suppressed
        // the whole time — by the time isSending is released the user message
        // save has almost always already completed and its ID has been synced.
        let userMessageId = UUID().uuidString
        let isFirstMessage = messages.isEmpty
        let capturedSessionId = sessionId
        let capturedAppId = overrideAppId ?? selectedAppId
        if !isFollowUp {
            // saveMessage site 3 of 5: user message at turn start.
            // Fire-and-forget Task launched before the bridge query so
            // it doesn't block streaming. `isSending` already gates the
            // poll until the AI response lands, but `pendingSaves`
            // provides defense-in-depth in case the save outlives the
            // bridge query (slow backend, retry, etc.).
            pendingSaves.begin()
            Task { [weak self] in
                do {
                    let response = try await APIClient.shared.saveMessage(
                        text: trimmedText,
                        sender: "human",
                        appId: capturedAppId,
                        sessionId: capturedSessionId,
                        metadata: attachmentMetadataJSON,
                        clientMessageId: userMessageId
                    )
                    // Adopt the server ID (local UUID → server ID) and mark synced.
                    // isSynced=true enables rating buttons on the message bubble.
                    await MainActor.run {
                        if let index = self?.messages.firstIndex(where: { $0.id == userMessageId }) {
                            self?.messages[index].id = response.id
                            self?.messages[index].isSynced = true
                        }
                        self?.pendingSaves.end()
                    }
                    log("Saved user message to backend: \(response.id)")
                } catch {
                    await MainActor.run { self?.pendingSaves.end() }
                    logError("Failed to persist user message", error: error)
                    // Non-critical - continue with chat
                }
            }

            let userMessage = ChatMessage(
                id: userMessageId,
                clientTurnId: clientTurnId,
                text: trimmedText,
                sender: .user,
                attachments: attachmentsForMessage
            )
            messages.append(userMessage)
            // Signal to ChatMessagesView after the local user row exists so
            // it anchors the new turn, not the previous one.
            localSendToken = LocalSendToken(generation: sendGeneration)

            // Track onboarding user messages with full content
            if isOnboarding {
                AnalyticsManager.shared.onboardingChatMessageDetailed(
                    role: "user", text: trimmedText, step: "chat"
                )
            }
        }

        let resolvedSurface = querySurface(
            surfaceRef: surfaceRef,
            sessionId: sessionId,
            systemPromptStyle: systemPromptStyle
        )
        await backfillConversationTurnsIfNeeded(for: resolvedSurface)

        // Create a placeholder AI message shown immediately in the UI while
        // streaming. It starts with a local UUID (isSynced=false, no rating buttons).
        // Lifecycle: local UUID → streaming text appended token by token →
        // isStreaming=false → isSending=false → backend save → ID replaced with
        // server ID, isSynced=true (rating buttons appear).
        let aiMessageId = UUID().uuidString
        let aiMessage = ChatMessage(
            id: aiMessageId,
            clientTurnId: clientTurnId,
            text: "",
            sender: .ai,
            isStreaming: true
        )
        messages.append(aiMessage)

        // Analytics: track timing and tool usage
        let queryStartTime = Date()
        var toolNames: [String] = []
        var toolStartTimes: [String: Date] = [:]
        let responseMetrics = ChatResponseMetrics()
        var completedResponseText: String?

        // Stall detection.
        // The detector observes every bridge event (text deltas, tool
        // activity, etc.) and a 500ms periodic tick task surfaces stall
        // promotions even during silent gaps. Transitions become
        // ToolCallStatus updates on individual tool-call blocks; the
        // banner appears via ToolCallsGroup's hasStalledTool check.
        let turnStartMs = ChatProvider.monotonicNowMs()
        let stallDetector = StallDetector(
            thresholds: .v1Defaults,
            startedAtMs: turnStartMs
        )

        // Refresh memories each turn so <user_facts> stays current.
        await refreshMemoriesForPrompt()
        let promptContext = formatMemoriesSection()
        var stoppedByUser = false
        do {
            // Use the system prompt built at warmup. The agent bridge applies it only
            // at session/new; for the normal reused-session path it is ignored.
            // Passing it here ensures it is applied if the session was invalidated
            // (e.g. cwd change) and a new session/new is triggered mid-conversation.
            var systemPrompt: String
            if isOnboarding, let prefix = systemPromptPrefix, !prefix.isEmpty {
                // Onboarding uses its own prompt exclusively — the main chat prompt
                // contains rules like "don't ask follow-up questions" that conflict
                // with the onboarding deep-dive step.
                systemPrompt = prefix
            } else {
                if systemPromptStyle == .floating {
                    if isFloatingPillSurface(resolvedSurface) {
                        systemPrompt = buildFloatingBarSystemPrompt(
                            contextString: promptContext,
                            excludingToolNames: ["spawn_agent", "run_agent_and_wait"]
                        )
                    } else {
                        systemPrompt = buildFloatingBarSystemPrompt(contextString: promptContext)
                    }
                } else {
                    systemPrompt = buildSystemPrompt(contextString: promptContext, style: .main)
                }
                if let prefix = systemPromptPrefix, !prefix.isEmpty {
                    systemPrompt = prefix + "\n\n" + systemPrompt
                }
            }
            if let suffix = systemPromptSuffix, !suffix.isEmpty {
                systemPrompt += "\n\n" + suffix
            }
            // Note: coordinator route and completion delta are assembled by the kernel.

            // Auto-inject notification context: if the most recent AI message before
            // the user's new message is a proactive notification, tell Claude about it
            // so it can answer follow-up questions about the notification.
            // If the caller didn't provide explicit imageData (e.g. screen-capture
            // assistant), fall back to the first image attached by the user.
            var effectiveImageData = imageData
            if effectiveImageData == nil {
                effectiveImageData = attachmentsForMessage.first(where: { $0.isImage })?.data
            }
            if systemPromptSuffix == nil {
                // Find the last AI message before the user's current message
                let aiMessages = messages.filter { $0.sender == .ai && !$0.isStreaming }
                if let lastAI = aiMessages.last, let ctx = lastAI.notificationContext {
                    systemPrompt += "\n\n" + ctx
                    // Attach the notification screenshot if no other image is provided
                    if effectiveImageData == nil, let screenshotData = lastAI.notificationScreenshot {
                        effectiveImageData = screenshotData
                    }
                }
            }

            // Query the active bridge with streaming. Hermes and OpenClaw do not
            // accept Omi's Claude model aliases, so leave model choice to the
            // harness default when either native adapter is active.
            let usesNativeModelChoice = activeBridgeHarness == "hermes" || activeBridgeHarness == "openclaw"
            let effectiveRequestModel = usesNativeModelChoice ? nil : (model ?? modelOverride)

            // Callbacks for agent bridge
            //
            // QueryTracer: responseMetrics marks TTFT on the very first output of
            // any kind (text delta OR tool_use start). It also brackets the
            // text-streaming window so the `generation` span excludes tool time.
            let currentChatMode = chatMode
            let currentToolClientScope: String? = isFloatingPillSurface(resolvedSurface)
                ? AgentClientScope.floatingPill
                : nil
            // Kernel control tools (spawn_agent, list_agent_sessions, …) execute in
            // the Node runtime and only surface via tool_activity + tool_result_display.
            // Pair started input with completed output for QueryTracer.tool_executions.
            var pendingToolTraceInputs:
                [String: (name: String, inputJson: String, started: ContinuousClock.Instant)] = [:]
            let textDeltaHandler: AgentClient.TextDeltaHandler = { [weak self] delta in
                let nowMs = ChatProvider.monotonicNowMs()
                if responseMetrics.markFirstOutputIfNeeded() {
                    tracer?.end("ttft")
                    tracer?.markTTFT()
                }
                if responseMetrics.markGenerationStartedIfNeeded() {
                    tracer?.begin("generation")
                }
                Task { @MainActor [weak self] in
                    self?.appendToMessage(id: aiMessageId, text: delta)
                    let transitions = await stallDetector.step(kind: .other, atMs: nowMs)
                    self?.applyStallTransitions(messageId: aiMessageId, transitions: transitions)
                }
            }
            let toolCallHandler: AgentClient.ToolCallHandler = { callId, name, input in
                let toolCall = ToolCall(name: name, arguments: input, thoughtSignature: nil)
                let result = await ChatToolExecutor.execute(
                    toolCall,
                    originatingChatMode: currentChatMode,
                    originatingClientScope: currentToolClientScope)
                log("OMI tool \(name) executed for callId=\(callId)")
                responseMetrics.recordToolResult(name: name, result: result)
                return result
            }
            let toolActivityHandler: AgentClient.ToolActivityHandler = { [weak self] name, status, toolUseId, input in
                let nowMs = ChatProvider.monotonicNowMs()
                // Tools without a toolUseId still get tracked under a
                // synthetic key so the detector's per-tool timer fires.
                let trackedId = ChatProvider.stallTrackingId(toolUseId: toolUseId, name: name)
                let toolStatus = ChatProvider.mapBridgeToolStatus(status)
                let detectorKind: StallDetector.EventKind = toolStatus == .running
                    ? .toolStarted(id: trackedId)
                    : .toolCompleted(id: trackedId)
                // QueryTracer: a span per tool invocation, keyed by toolUseId so
                // concurrent calls to the same tool don't collide. Overlapping
                // start/end windows across spans reveal parallel vs sequential
                // tool execution. A tool_use start also counts as first output
                // for TTFT when the model leads with a tool call (no text first).
                let spanKey = "tool:\(toolUseId ?? name)"
                if status == "started" {
                    if responseMetrics.markFirstOutputIfNeeded() {
                        tracer?.end("ttft")
                        tracer?.markTTFT()
                    }
                    tracer?.begin(spanKey, metadata: ["tool": name])
                    if let input {
                        let inputJson =
                            (try? String(data: JSONSerialization.data(withJSONObject: input), encoding: .utf8))
                            ?? "\(input)"
                        pendingToolTraceInputs[trackedId] = (name, inputJson, ContinuousClock.now)
                    }
                } else if toolStatus != .running {
                    tracer?.end(spanKey)
                }
                Task { @MainActor [weak self] in
                    self?.addToolActivity(
                        messageId: aiMessageId,
                        toolName: name,
                        status: toolStatus,
                        toolUseId: toolUseId,
                        input: input
                    )
                    if toolStatus == .running {
                        toolNames.append(name)
                        toolStartTimes[trackedId] = Date()
                        if (name.contains("browser") || name.contains("playwright")) {
                            let token = UserDefaults.standard.string(forKey: "playwrightExtensionToken") ?? ""
                            if token.isEmpty {
                                log("ChatProvider: Browser tool \(name) called without extension token — aborting query and prompting setup")
                                self?.needsBrowserExtensionSetup = true
                                self?.stopAgent(owner: turnOwner)
                                // Keep floating-bar sessions non-intrusive: do not foreground
                                // the main window when the query originated from the floating bar.
                                if systemPromptStyle != .floating {
                                    // Bring the app to the foreground so the setup sheet is visible
                                    // (the failed browser attempt may have opened Chrome, stealing focus)
                                    NSApp.activate()
                                    for window in NSApp.windows where window.title.hasPrefix("Omi") {
                                        window.makeKeyAndOrderFront(nil)
                                    }
                                }
                            }
                            // Show the floating bar so the user has an always-on-top UI
                            // when Chrome takes focus (important on small screens)
                            if !FloatingControlBarManager.shared.isVisible {
                                log("ChatProvider: Browser tool active — showing floating bar so it stays above Chrome")
                                FloatingControlBarManager.shared.showTemporarily()
                            }
                        }
                    } else if let startTime = toolStartTimes.removeValue(forKey: trackedId) {
                        if toolStatus == .completed {
                            let durationMs = Int(Date().timeIntervalSince(startTime) * 1000)
                            AnalyticsManager.shared.chatToolCallCompleted(toolName: name, durationMs: durationMs)
                        }
                    }
                    let transitions = await stallDetector.step(kind: detectorKind, atMs: nowMs)
                    self?.applyStallTransitions(messageId: aiMessageId, transitions: transitions)
                }
            }
            let thinkingDeltaHandler: AgentClient.ThinkingDeltaHandler = { [weak self] text in
                let nowMs = ChatProvider.monotonicNowMs()
                Task { @MainActor [weak self] in
                    self?.appendThinking(messageId: aiMessageId, text: text)
                    let transitions = await stallDetector.step(kind: .other, atMs: nowMs)
                    self?.applyStallTransitions(messageId: aiMessageId, transitions: transitions)
                }
            }
            let toolResultDisplayHandler: AgentClient.ToolResultDisplayHandler = { [weak self] toolUseId, name, output in
                let nowMs = ChatProvider.monotonicNowMs()
                if let tracer {
                    let trackedId = ChatProvider.stallTrackingId(toolUseId: toolUseId, name: name)
                    let pending = pendingToolTraceInputs.removeValue(forKey: trackedId)
                    let inputJson = pending?.inputJson ?? ""
                    let durationMs = pending.map { (ContinuousClock.now - $0.started).milliseconds }
                    tracer.captureToolExecution(
                        toolUseId: toolUseId.isEmpty ? nil : toolUseId,
                        name: name,
                        input: inputJson,
                        output: output,
                        durationMs: durationMs
                    )
                }
                Task { @MainActor [weak self] in
                    self?.addToolResult(messageId: aiMessageId, toolUseId: toolUseId, name: name, output: output)
                    let transitions = await stallDetector.step(kind: .other, atMs: nowMs)
                    self?.applyStallTransitions(messageId: aiMessageId, transitions: transitions)
                }
            }

            // Periodic tick task surfaces stall promotions during silent
            // gaps when no bridge events arrive. Cancelled via defer on
            // scope exit (success or throw).
            let stallTickTask = Task { [weak self] in
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 500_000_000)  // 500ms
                    if Task.isCancelled { break }
                    let nowMs = ChatProvider.monotonicNowMs()
                    let transitions = await stallDetector.tick(atMs: nowMs)
                    if transitions.isEmpty { continue }
                    await MainActor.run { [weak self] in
                        self?.applyStallTransitions(messageId: aiMessageId, transitions: transitions)
                    }
                }
            }
            defer { stallTickTask.cancel() }

            // QueryTracer: snapshot the exact request (system prompt + recent
            // message history) and open the request/TTFT spans. The clock starts
            // here so ttft measures input → first streamed output.
            if let tracer {
                let tracedModel = effectiveRequestModel ?? "unknown"
                tracer.captureRequest(
                    systemPrompt: systemPrompt,
                    messages: Array(messages.suffix(40)).map {
                        ["role": $0.sender == .user ? "user" : "assistant", "content": $0.text]
                    },
                    hasScreenshot: effectiveImageData != nil
                )
                tracer.begin("llm_request", metadata: ["model": tracedModel])
                tracer.begin("ttft")
            }

            activeBridgeSendGeneration = sendGen
            let queryResult = try await resolvedAgentClient().query(
                prompt: trimmedText,
                systemPrompt: systemPrompt,
                surface: resolvedSurface,
                cwd: effectiveAgentWorkingDirectory(),
                mode: chatMode.rawValue,
                model: effectiveRequestModel,
                imageData: effectiveImageData,
                attachmentMetadataJson: Self.attachmentContextPrompt(for: attachmentsForMessage),
                onTextDelta: textDeltaHandler,
                onToolCall: toolCallHandler,
                onToolActivity: toolActivityHandler,
                onThinkingDelta: thinkingDeltaHandler,
                onToolResultDisplay: toolResultDisplayHandler,
                onAuthRequired: { [weak self] methods, authUrl in
                    Task { @MainActor [weak self] in
                        self?.claudeAuthMethods = methods
                        self?.claudeAuthUrl = authUrl
                        self?.isClaudeAuthRequired = true
                    }
                },
                onAuthSuccess: { [weak self] in
                    Task { @MainActor [weak self] in
                        self?.isClaudeAuthRequired = false
                        self?.checkClaudeConnectionStatus()
                    }
                }
            )
            activeBridgeSendGeneration = nil
            // Flush any remaining buffered streaming text before finalizing
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
            flushStreamingBuffer()

            // Determine the final text to display and save
            let messageText: String
            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                // Message still in memory — update it in-place
                messageText = messages[index].text.isEmpty ? queryResult.text : messages[index].text
                let metricsSnapshot = responseMetrics.snapshot()
                messages[index].text = messageText
                messages[index].isStreaming = false
                // Merge the parent agent's own artifacts with any produced by
                // sub-agents that completed since the last coordinator check, so
                // a finished sub-agent's file surfaces as a card on this response.
                let deltaResources = queryResult.completionDeltaArtifacts.map(ChatResource.artifact)
                messages[index].resources = mergedResources(
                    existing: messages[index].resources,
                    adding: queryResult.artifacts.map(ChatResource.artifact) + deltaResources
                )
                messages[index].metadata = MessageMetadata(
                    model: effectiveRequestModel,
                    inputTokens: queryResult.inputTokens,
                    outputTokens: queryResult.outputTokens,
                    cacheReadTokens: queryResult.cacheReadTokens,
                    cacheWriteTokens: queryResult.cacheWriteTokens,
                    costUsd: queryResult.costUsd,
                    systemPrompt: systemPrompt,
                    hasScreenshot: imageData != nil,
                    screenshotSizeBytes: imageData?.count,
                    toolNames: toolNames,
                    sqlRowsReturned: metricsSnapshot.sqlRowsReturned,
                    sqlQueryCount: metricsSnapshot.sqlQueryCount
                )
                completeRemainingToolCalls(messageId: aiMessageId, terminalStatus: .completed)
            } else {
                // Message no longer in memory (user switched away from this session).
                messageText = queryResult.text
                log("Chat response arrived after session switch")
            }

            // QueryTracer: success path — record the response, close the remaining
            // spans (end calls are no-ops if already closed), and write the trace
            // with real token / cache / cost numbers from the bridge result.
            tracer?.captureResponse(text: messageText)
            tracer?.end("ttft")
            tracer?.end("generation")
            tracer?.end("llm_request")
            tracer?.finalize(
                tokenCount: queryResult.outputTokens,
                model: effectiveRequestModel,
                inputTokens: queryResult.inputTokens,
                outputTokens: queryResult.outputTokens,
                cacheReadTokens: queryResult.cacheReadTokens,
                cacheWriteTokens: queryResult.cacheWriteTokens,
                costUsd: queryResult.costUsd
            )

            // Release the sending lock as soon as the AI response is visible in the
            // UI. Backend persistence is slow (can timeout at 30s+) and should not
            // block the user from making new queries to Claude.
            //
            // IMPORTANT: releasing isSending here opens a race window with the poll
            // timer. The poll can now fetch backend messages while saveMessage() is
            // still in-flight. The AI message still has a local UUID at this point
            // (isSynced=false). pollForNewMessages() handles this by merging the
            // backend copy into the local message rather than appending a duplicate.
            releaseSendLock(sendGeneration: sendGen)

            // Save AI response to backend. aiMessageId is captured above so we can
            // locate the right message even if the user has started a new query by
            // the time this completes.
            //
            // After save: update the in-memory message's ID from local UUID to the
            // server-assigned ID, and mark isSynced=true. This is the normal path
            // (no race). The poll's merge logic handles the case where the poll fires
            // before this update runs.
            let textToSave = queryResult.text.isEmpty ? messageText : queryResult.text
            if !textToSave.isEmpty {
                // saveMessage site 4 of 5 (THE CRITICAL ONE): AI
                // response on the success path. `isSending=false` was
                // already released a few lines above to unblock the
                // next query, so the poll could fire DURING this await
                // and observe the just-saved AI message before the
                // local UUID has been updated to the server ID below.
                // The counter closes that window — `pendingSaves`
                // stays active until the save lands AND the in-memory
                // ID has been synced. The pre-existing 200-char
                // text-prefix merge at `pollForNewMessages` stays as
                // a secondary safety net.
                // `defer` guarantees the counter is released on every exit
                // path — success, throw, or any future early return added
                // inside this block — so a missed `end()` can't permanently
                // suppress the poll.
                pendingSaves.begin()
                defer { pendingSaves.end() }
                do {
                    let toolMetadata = serializeMessagePersistenceMetadata(messageId: aiMessageId)
                    let response = try await APIClient.shared.saveMessage(
                        text: textToSave,
                        sender: "ai",
                        appId: capturedAppId,
                        sessionId: capturedSessionId,
                        metadata: toolMetadata,
                        clientMessageId: aiMessageId
                    )
                    // Adopt the server ID so future polls find this message by ID
                    // (existingIds check in pollForNewMessages). isSynced=true enables
                    // thumbs-up/down rating UI.
                    if let syncIndex = messages.firstIndex(where: { $0.id == aiMessageId }) {
                        messages[syncIndex].id = response.id
                        messages[syncIndex].isSynced = true
                    }
                    log("Saved and synced AI response: \(response.id) (session=\(capturedSessionId ?? "nil"), tool_calls=\(toolMetadata != nil ? "yes" : "none"))")
                } catch {
                    logError("Failed to persist AI response", error: error)
                }
            }

            // Auto-generate title after first exchange (user message + AI response)
            if isFirstMessage, let sid = capturedSessionId {
                await generateSessionTitle(sessionId: sid)
            }

            log("Chat response complete")

            // Track onboarding AI responses with full content and tool calls
            if isOnboarding {
                let aiText = messages.first(where: { $0.id == aiMessageId })?.text ?? queryResult.text
                AnalyticsManager.shared.onboardingChatMessageDetailed(
                    role: "assistant",
                    text: aiText,
                    step: "chat",
                    toolCalls: toolNames.isEmpty ? nil : toolNames,
                    model: effectiveRequestModel
                )
            }

            // Analytics: track query completion
            let durationMs = Int(Date().timeIntervalSince(queryStartTime) * 1000)
            let responseLength = messages.first(where: { $0.id == aiMessageId })?.text.count ?? 0
            AnalyticsManager.shared.chatAgentQueryCompleted(
                durationMs: durationMs,
                toolCallCount: toolNames.count,
                toolNames: toolNames,
                costUsd: queryResult.costUsd,
                messageLength: responseLength
            )

            // Skip client-side cost telemetry for piMono because /v2/chat/completions
            // already logs Omi-account token/cost usage server-side. Question
            // quota is recorded by the backend when the accepted human message
            // is persisted, so model calls and helper calls cannot double-count. Local harnesses
            // (Hermes/OpenClaw) skip telemetry entirely; use the actual harness, not
            // @AppStorage bridgeMode, because directed Hermes/OpenClaw pills can
            // override the harness without changing the user's global preference.
            let effectiveHarness = activeBridgeHarness
            let isPiMonoHarness = effectiveHarness == Self.harnessMode(for: .piMono)
            let isUserClaudeHarness = effectiveHarness == Self.harnessMode(for: .userClaude)
            if isUserClaudeHarness {
                let r = queryResult
                Task.detached(priority: .background) {
                    await APIClient.shared.recordLlmUsage(
                        inputTokens: r.inputTokens,
                        outputTokens: r.outputTokens,
                        cacheReadTokens: r.cacheReadTokens,
                        cacheWriteTokens: r.cacheWriteTokens,
                        totalTokens: r.inputTokens + r.outputTokens + r.cacheReadTokens + r.cacheWriteTokens,
                        costUsd: r.costUsd,
                        account: "personal"
                    )
                }
            }
            if isPiMonoHarness {
                sessionTokensUsed += queryResult.inputTokens + queryResult.outputTokens
                omiAICumulativeCostUsd += queryResult.costUsd
                // Show the upgrade flow when the free Omi usage threshold is reached.
                // Never for paid/BYOK users — they aren't subject to the free Omi spend cap.
                if omiAICumulativeCostUsd >= 50.0 && !isExemptFromOmiUpgradeNudge {
                    showOmiThresholdAlert = true
                }
            }

            // Fire-and-forget: check if user's message mentions goal progress
            let chatText = trimmedText
            Task.detached(priority: .background) {
                await GoalsAIService.shared.extractProgressFromAllGoals(text: chatText)
            }
            completedResponseText = messageText
        } catch {
            activeBridgeSendGeneration = nil
            // QueryTracer: error path — close spans and write the (partial) trace
            // so failed/timed-out queries still show up in benchmarks.
            tracer?.end("ttft")
            tracer?.end("generation")
            tracer?.end("llm_request")
            tracer?.finalize(tokenCount: 0, model: model ?? modelOverride)

            // On timeout, cancel the stuck ACP session so it's not left dangling
            if let bridgeError = error as? BridgeError, case .timeout = bridgeError {
                log("ChatProvider: ACP query timed out, sending interrupt to cancel stuck session")
                await resolvedAgentClient().interrupt()
            }

            // Flush any remaining buffered streaming text before handling the error
            streamingFlushWorkItem?.cancel()
            streamingFlushWorkItem = nil
            flushStreamingBuffer()

            // Only remove the AI message if it's still empty (no streamed text yet).
            // If text was already streamed and visible, keep it and just stop streaming.
            if let index = messages.firstIndex(where: { $0.id == aiMessageId }) {
                if messages[index].text.isEmpty && messages[index].contentBlocks.isEmpty {
                    messages.remove(at: index)
                } else {
                    messages[index].isStreaming = false
                    completeRemainingToolCalls(
                        messageId: aiMessageId,
                        terminalStatus: ChatProvider.remainingToolStatusAfterPartialResponseError(error)
                    )
                    log("Bridge error after partial response — keeping \(messages[index].text.count) chars of streamed text")
                    // Still try to persist the partial response.
                    //
                    // saveMessage site 5 of 5: partial AI
                    // response after a bridge error. Fire-and-forget
                    // Task; same counter pattern as the other sites.
                    let partialText = messages[index].text
                    let partialToolMetadata = self.serializeMessagePersistenceMetadata(messageId: aiMessageId)
                    pendingSaves.begin()
                    Task { [weak self] in
                        do {
                            let response = try await APIClient.shared.saveMessage(
                                text: partialText,
                                sender: "ai",
                                appId: capturedAppId,
                                sessionId: capturedSessionId,
                                metadata: partialToolMetadata,
                                clientMessageId: aiMessageId
                            )
                            await MainActor.run {
                                if let syncIndex = self?.messages.firstIndex(where: { $0.id == aiMessageId }) {
                                    self?.messages[syncIndex].id = response.id
                                    self?.messages[syncIndex].isSynced = true
                                }
                                self?.pendingSaves.end()
                            }
                            log("Saved partial AI response to backend: \(response.id)")
                        } catch {
                            await MainActor.run { self?.pendingSaves.end() }
                            logError("Failed to persist partial AI response", error: error)
                        }
                    }
                }
            }

            logError("Failed to get AI response", error: error)
            // Send both user-friendly and raw error to analytics for remote debugging
            let rawError: String
            if let bridgeError = error as? BridgeError {
                rawError = String(describing: bridgeError)
            } else {
                rawError = "\(error)"
            }
            AnalyticsManager.shared.chatAgentError(error: error.localizedDescription, rawError: rawError)

            // Track onboarding errors with full context
            if isOnboarding {
                AnalyticsManager.shared.onboardingChatMessageDetailed(
                    role: "error", text: trimmedText, step: "chat",
                    error: rawError
                )
            }

            // Show error to user (unless they intentionally stopped).
            //
            // Prefer the structured ChatErrorState card when the error
            // maps cleanly. Falls through to the legacy errorMessage
            // banner for unmappable BridgeError cases (encodingError,
            // quotaExceeded, .agentError with a free-form message).
            // Both surfaces coexist — only one is active at a time per
            // turn.
            if let bridgeError = error as? BridgeError, case .stopped = bridgeError {
                stoppedByUser = true
                // User stopped — no error to show, but the card system
                // still surfaces .interrupted so users can resume.
                if let card = ChatErrorState.from(bridgeError) {
                    currentError = card
                    lastFailedPrompt = trimmedText
                    errorMessage = nil
                }
            } else if let bridgeError = error as? BridgeError,
                      let card = ChatErrorState.from(bridgeError) {
                currentError = card
                lastFailedPrompt = trimmedText
                errorMessage = nil
            } else {
                errorMessage = error.localizedDescription
                currentError = nil  // ensure the card is dismissed if it was up
            }
        }

        let releasedCurrentGeneration: Bool
        if stoppedByUser, isStopping, sendGeneration != sendGen {
            clearSendLockState()
            releasedCurrentGeneration = false
        } else {
            releasedCurrentGeneration = releaseSendLock(sendGeneration: sendGen)
        }

        // If follow-ups were queued while we were running, chain the oldest as a new full query.
        // Each chained query drains one item; this preserves user barge-in order without
        // recursively starting overlapping bridge queries.
        if releasedCurrentGeneration, !pendingFollowUps.isEmpty {
            let followUp = pendingFollowUps.removeFirst()
            log("ChatProvider: chaining follow-up query")
            await sendMessage(
                followUp.text,
                model: followUp.model,
                isFollowUp: true,
                systemPromptSuffix: followUp.systemPromptSuffix,
                systemPromptPrefix: followUp.systemPromptPrefix,
                systemPromptStyle: followUp.systemPromptStyle,
                surfaceRef: followUp.surfaceRef,
                turnOwner: followUp.turnOwner
            )
        }
        return completedResponseText
    }

    @discardableResult
    private func releaseSendLock(sendGeneration generation: Int) -> Bool {
        guard sendGeneration == generation else { return false }
        clearSendLockState()
        return true
    }

    private func clearSendLockState() {
        isSending = false
        isStopping = false
        activeBridgeSendGeneration = nil
        activeTurnOwner = nil
        activeFollowUpContext = nil
        if let prompt = pendingErrorRecoveryPrompt {
            pendingErrorRecoveryPrompt = nil
            Task { [weak self] in
                await self?.sendMessage(prompt)
            }
        }
    }

    /// Generate a title for the session using LLM
    private func generateSessionTitle(sessionId: String) async {
        // Need at least 2 messages (user + AI) for meaningful title
        guard messages.count >= 2 else {
            log("Not enough messages for title generation")
            return
        }

        // Convert messages to the format expected by the API
        let messageTuples: [(text: String, sender: String)] = messages.map { msg in
            (text: msg.text, sender: msg.sender == .user ? "human" : "ai")
        }

        do {
            let response = try await APIClient.shared.generateSessionTitle(
                sessionId: sessionId,
                messages: messageTuples
            )

            // Update session in list
            if let index = sessions.firstIndex(where: { $0.id == sessionId }) {
                sessions[index].title = response.title
            }

            // Update current session
            if currentSession?.id == sessionId {
                currentSession?.title = response.title
            }

            log("Generated session title: \(response.title)")
            AnalyticsManager.shared.sessionTitleGenerated()
        } catch {
            logError("Failed to generate session title", error: error)
            // Non-fatal - session continues with default title
        }
    }

    /// Update message text (replaces entire text)
    private func updateMessage(id: String, text: String) {
        if let index = messages.firstIndex(where: { $0.id == id }) {
            if messages[index].sender == .ai {
                messages[index].text = normalizeAssistantSentenceSpacing(text)
            } else {
                messages[index].text = text
            }
        }
    }

    /// Normalize missing spaces after sentence punctuation in assistant messages.
    /// Example: "Hello.World" -> "Hello. World", "Great!Lets go" -> "Great! Lets go"
    private func normalizeAssistantSentenceSpacing(_ text: String) -> String {
        var normalized = text

        if let punctuationUpper = try? NSRegularExpression(pattern: #"([.!?])(?=[A-Z])"#) {
            let range = NSRange(normalized.startIndex..., in: normalized)
            normalized = punctuationUpper.stringByReplacingMatches(in: normalized, options: [], range: range, withTemplate: "$1 ")
        }

        if let punctuationQuotedUpper = try? NSRegularExpression(pattern: #"([.!?])(?=[\"“'‘][A-Z])"#) {
            let range = NSRange(normalized.startIndex..., in: normalized)
            normalized = punctuationQuotedUpper.stringByReplacingMatches(in: normalized, options: [], range: range, withTemplate: "$1 ")
        }

        return normalized
    }

    /// Append text to a streaming message via a buffer that flushes at ~100ms intervals.
    /// This reduces SwiftUI re-renders from once-per-token to ~10 times/second.
    private func appendToMessage(id: String, text: String) {
        streamingBufferMessageId = id
        streamingTextBuffer += text

        // Schedule a flush if one isn't already pending
        if streamingFlushWorkItem == nil {
            let workItem = DispatchWorkItem { [weak self] in
                self?.flushStreamingBuffer()
            }
            streamingFlushWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + streamingFlushInterval, execute: workItem)
        }
    }

    /// Flush accumulated text and thinking deltas to the published messages array.
    private func flushStreamingBuffer() {
        streamingFlushWorkItem = nil

        guard let id = streamingBufferMessageId,
              let index = messages.firstIndex(where: { $0.id == id }) else {
            streamingTextBuffer = ""
            streamingThinkingBuffer = ""
            return
        }

        // Flush text buffer
        if !streamingTextBuffer.isEmpty {
            let buffered = streamingTextBuffer
            streamingTextBuffer = ""

            messages[index].text += buffered
            if messages[index].sender == .ai {
                messages[index].text = normalizeAssistantSentenceSpacing(messages[index].text)
            }

            if let lastBlockIndex = messages[index].contentBlocks.indices.last,
               case .text(let blockId, let existing) = messages[index].contentBlocks[lastBlockIndex] {
                let merged = existing + buffered
                let blockText = messages[index].sender == .ai ? normalizeAssistantSentenceSpacing(merged) : merged
                messages[index].contentBlocks[lastBlockIndex] = .text(id: blockId, text: blockText)
            } else {
                let blockText = messages[index].sender == .ai ? normalizeAssistantSentenceSpacing(buffered) : buffered
                messages[index].contentBlocks.append(.text(id: UUID().uuidString, text: blockText))
            }
        }

        // Flush thinking buffer
        if !streamingThinkingBuffer.isEmpty {
            let buffered = streamingThinkingBuffer
            streamingThinkingBuffer = ""

            if let lastBlockIndex = messages[index].contentBlocks.indices.last,
               case .thinking(let thinkId, let existing) = messages[index].contentBlocks[lastBlockIndex] {
                messages[index].contentBlocks[lastBlockIndex] = .thinking(id: thinkId, text: existing + buffered)
            } else {
                messages[index].contentBlocks.append(.thinking(id: UUID().uuidString, text: buffered))
            }
        }
    }

    /// Add a tool call indicator to a streaming message
    /// Append a discovery card block to the last AI message in the chat
    func appendDiscoveryCard(title: String, summary: String, fullText: String) {
        guard let index = messages.lastIndex(where: { $0.sender == .ai }) else { return }
        messages[index].contentBlocks.append(
            .discoveryCard(id: UUID().uuidString, title: title, summary: summary, fullText: fullText)
        )
    }

    private func addToolActivity(messageId: String, toolName: String, status: ToolCallStatus, toolUseId: String? = nil, input: [String: Any]? = nil) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
        ToolCallBlockUpdater.applyToolActivity(
            to: &messages[index].contentBlocks,
            toolName: toolName,
            status: status,
            toolUseId: toolUseId,
            input: input
        )
        if status == .completed {
            attachGeneratedFileResources(
                messageIndex: index,
                toolName: toolName,
                toolUseId: toolUseId,
                extraTexts: []
            )
        }
    }

    /// Add tool result output to an existing tool call block
    private func addToolResult(messageId: String, toolUseId: String, name: String, output: String) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
        ToolCallBlockUpdater.applyToolOutput(
            to: &messages[index].contentBlocks,
            toolUseId: toolUseId,
            name: name,
            output: output
        )
        attachGeneratedFileResources(
            messageIndex: index,
            toolName: name,
            toolUseId: toolUseId,
            extraTexts: [output]
        )
    }

    private func attachGeneratedFileResources(
        messageIndex index: Int,
        toolName: String,
        toolUseId: String?,
        extraTexts: [String]
    ) {
        let discoveredResources = localFileResources(
            fromToolName: toolName,
            texts: toolResourceCandidateTexts(
                in: messages[index].contentBlocks,
                toolName: toolName,
                toolUseId: toolUseId,
                extraTexts: extraTexts
            )
        )
        if !discoveredResources.isEmpty {
            messages[index].resources = mergedResources(
                existing: messages[index].resources,
                adding: discoveredResources
            )
        }
    }

    private func mergedResources(existing: [ChatResource], adding newResources: [ChatResource]) -> [ChatResource] {
        guard !newResources.isEmpty else { return existing }
        var seen = Set(existing.map(\.id))
        var merged = existing
        for resource in newResources where !seen.contains(resource.id) {
            seen.insert(resource.id)
            merged.append(resource)
        }
        return merged
    }

    private func toolResourceCandidateTexts(
        in blocks: [ChatContentBlock],
        toolName: String,
        toolUseId: String?,
        extraTexts: [String]
    ) -> [String] {
        let normalizedToolUseId = toolUseId?.isEmpty == false ? toolUseId : nil
        var texts = extraTexts
        for block in blocks {
            guard case .toolCall(_, let blockName, _, let blockToolUseId, let input, let output) = block else {
                continue
            }
            let idsMatch = normalizedToolUseId != nil && blockToolUseId == normalizedToolUseId
            let namesMatch = Self.normalizedToolNameHead(blockName) == Self.normalizedToolNameHead(toolName)
            guard idsMatch || (normalizedToolUseId == nil && namesMatch) else {
                continue
            }
            if let summary = input?.summary {
                texts.append(summary)
            }
            if let details = input?.details {
                texts.append(details)
            }
            if let output {
                texts.append(output)
            }
        }
        return texts
    }

    private func localFileResources(fromToolName name: String, texts: [String]) -> [ChatResource] {
        let normalizedName = Self.normalizedToolNameHead(name)
        guard ["write", "edit", "multiedit"].contains(normalizedName) else { return [] }
        return localFileURLs(from: texts.joined(separator: "\n")).map { url in
            let mimeType = mimeType(forLocalFile: url)
            return ChatResource.localGeneratedFile(
                id: "generated-file:\(url.path)",
                title: url.lastPathComponent,
                subtitle: localFileSubtitle(url: url, mimeType: mimeType),
                mimeType: mimeType,
                uri: url.absoluteString
            )
        }
    }

    private func localFileURLs(from output: String) -> [URL] {
        let pattern = #"(?:"file://)?(/[^\n"`]+)"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let nsRange = NSRange(output.startIndex..<output.endIndex, in: output)
        var urls: [URL] = []
        var seen = Set<String>()
        for match in regex.matches(in: output, range: nsRange) {
            guard match.numberOfRanges > 1,
                  let range = Range(match.range(at: 1), in: output)
            else { continue }
            let rawPath = String(output[range])
                .trimmingCharacters(in: CharacterSet(charactersIn: " \t\r\n.。,:;)'\"]"))
            let url = URL(fileURLWithPath: rawPath)
            var isDirectory: ObjCBool = false
            guard FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory),
                  !isDirectory.boolValue,
                  !seen.contains(url.path)
            else { continue }
            seen.insert(url.path)
            urls.append(url)
        }
        return urls
    }

    private static func normalizedToolNameHead(_ name: String) -> String {
        let normalized = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.split(separator: ":", maxSplits: 1).first.map(String.init) ?? normalized
    }

    private func mimeType(forLocalFile url: URL) -> String {
        if let type = UTType(filenameExtension: url.pathExtension),
           let mime = type.preferredMIMEType {
            return mime
        }
        return "application/octet-stream"
    }

    private func localFileSubtitle(url: URL, mimeType: String) -> String {
        var parts = [mimeType]
        if let attrs = try? FileManager.default.attributesOfItem(atPath: url.path),
           let size = attrs[.size] as? NSNumber {
            parts.append(ByteCountFormatter.string(fromByteCount: size.int64Value, countStyle: .file))
        }
        return parts.joined(separator: " • ")
    }

    /// Append thinking text to the streaming message via the shared buffer.
    private func appendThinking(messageId: String, text: String) {
        streamingBufferMessageId = messageId
        streamingThinkingBuffer += text

        // Schedule a flush if one isn't already pending
        if streamingFlushWorkItem == nil {
            let workItem = DispatchWorkItem { [weak self] in
                self?.flushStreamingBuffer()
            }
            streamingFlushWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + streamingFlushInterval, execute: workItem)
        }
    }

    /// Mark any remaining in-flight tool call blocks as terminal in a message.
    /// Called when a query finishes (success or interrupt) so spinners don't spin forever.
    /// Matches `.running`, `.slow`, and `.stalled` (any state where `isInFlight` is true)
    /// so detector-promoted blocks resolve when the turn ends.
    private func completeRemainingToolCalls(messageId: String, terminalStatus: ToolCallStatus = .completed) {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return }
        ToolCallBlockUpdater.completeRemainingToolCalls(
            in: &messages[index].contentBlocks,
            terminalStatus: terminalStatus
        )
    }

    /// Monotonic millisecond timestamp for elapsed-time stall detection.
    /// Unlike wall-clock time, system uptime is unaffected by NTP or
    /// manual clock changes.
    nonisolated private static func monotonicNowMs() -> Int {
        Int(ProcessInfo.processInfo.systemUptime * 1000)
    }

    /// The key the `StallDetector` tracks a tool under. Tools that arrive
    /// without a real `toolUseId` fall back to a name-derived synthetic
    /// key so their per-tool timer still fires. Registration (in the tool
    /// activity handler) and the transition match in `applyStallTransitions`
    /// MUST derive the key identically — routing both through this single
    /// helper keeps them from diverging (a mismatch silently drops every
    /// stall transition for `toolUseId`-less tools).
    nonisolated static func stallTrackingId(toolUseId: String?, name: String) -> String {
        toolUseId ?? "untracked-\(name)"
    }

    nonisolated static func mapBridgeToolStatus(_ status: String) -> ToolCallStatus {
        switch status {
        case "started":
            return .running
        case "failed", "cancelled", "interrupted":
            return .failed
        default:
            return .completed
        }
    }

    /// Intentional user stops should not make in-flight tool rows look
    /// like execution errors. Real bridge failures still surface as failed.
    nonisolated static func remainingToolStatusAfterPartialResponseError(_ error: Error) -> ToolCallStatus {
        if let bridgeError = error as? BridgeError, case .stopped = bridgeError {
            return .completed
        }
        return .failed
    }

    /// Map a `StallDetector.State` to the matching `ToolCallStatus`.
    /// The two enums are deliberately separate — the detector tracks a
    /// 3-state lifecycle independent of UI/persistence concerns.
    private func mapDetectorState(_ state: StallDetector.State) -> ToolCallStatus {
        switch state {
        case .running: return .running
        case .slow: return .slow
        case .stalled: return .stalled
        }
    }

    /// Apply detector transitions to the message's tool-call blocks.
    /// Only `.tool(id:from:to:)` transitions are surfaced in the UI;
    /// `.interEvent` transitions are observed but not rendered here.
    private func applyStallTransitions(
        messageId: String,
        transitions: [StallDetector.Transition]
    ) {
        guard !transitions.isEmpty,
              let index = messages.firstIndex(where: { $0.id == messageId }) else { return }

        for transition in transitions {
            guard case .tool(let id, _, let to) = transition else { continue }
            for i in messages[index].contentBlocks.indices {
                if case .toolCall(let blockId, let name, let oldStatus, let tuid, let input, let output) = messages[index].contentBlocks[i],
                   ChatProvider.stallTrackingId(toolUseId: tuid, name: name) == id,
                   oldStatus.isInFlight {
                    messages[index].contentBlocks[i] = .toolCall(
                        id: blockId, name: name, status: mapDetectorState(to),
                        toolUseId: tuid, input: input, output: output
                    )
                }
            }
        }
    }

    /// Serialize tool calls and resource cards from a message into a JSON metadata string.
    /// Returns nil if there are no tool calls and no resources.
    private func serializeMessagePersistenceMetadata(messageId: String) -> String? {
        guard let index = messages.firstIndex(where: { $0.id == messageId }) else { return nil }

        var root: [String: Any] = [:]

        var toolCalls: [[String: Any]] = []
        for block in messages[index].contentBlocks {
            if case .toolCall(_, let name, _, let toolUseId, let input, let output) = block {
                var call: [String: Any] = ["name": name]
                if let toolUseId = toolUseId { call["tool_use_id"] = toolUseId }
                if let input = input {
                    call["input_summary"] = input.summary
                    if let details = input.details { call["input"] = details }
                }
                if let output = output {
                    // Truncate large outputs to keep metadata reasonable
                    call["output"] = output.count > 500 ? String(output.prefix(500)) + "… (truncated)" : output
                }
                toolCalls.append(call)
            }
        }
        if !toolCalls.isEmpty {
            root["tool_calls"] = toolCalls
        }

        if let resourcesMetadata = ChatResource.mergeResourcesIntoMessageMetadata(
            nil,
            resources: messages[index].resources
        ),
           let data = resourcesMetadata.data(using: .utf8),
           let resourcesRoot = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let resources = resourcesRoot[ChatResource.messageMetadataResourcesKey] {
            root[ChatResource.messageMetadataResourcesKey] = resources
        }

        guard !root.isEmpty else { return nil }

        guard let data = try? JSONSerialization.data(withJSONObject: root),
              let json = String(data: data, encoding: .utf8) else { return nil }
        return json
    }

    /// Re-resolve artifact cards whose persisted file paths are missing by asking the kernel.
    private func rehydrateMissingArtifactResourcesFromKernel() async {
        var runIds = Set<String>()
        for message in messages {
            for resource in message.resources where resource.artifactId != nil {
                guard let fileURL = resource.fileURL else {
                    if let runId = resource.runId { runIds.insert(runId) }
                    continue
                }
                if !FileManager.default.fileExists(atPath: fileURL.path),
                   let runId = resource.runId {
                    runIds.insert(runId)
                }
            }
        }
        guard !runIds.isEmpty else { return }

        var artifactsByRunId: [String: [String: AgentArtifactProjection]] = [:]
        for runId in runIds {
            guard let artifacts = try? await DesktopCoordinatorService.shared.inspectArtifactsForRun(runId: runId)
            else { continue }
            artifactsByRunId[runId] = Dictionary(uniqueKeysWithValues: artifacts.map { ($0.artifactId, $0) })
        }
        guard !artifactsByRunId.isEmpty else { return }

        for messageIndex in messages.indices {
            var updatedResources = messages[messageIndex].resources
            var changed = false
            for resourceIndex in updatedResources.indices {
                let resource = updatedResources[resourceIndex]
                guard let artifactId = resource.artifactId,
                      let runId = resource.runId,
                      let artifact = artifactsByRunId[runId]?[artifactId]
                else { continue }

                let refreshed = resource.refreshedFromKernelArtifact(artifact)
                if refreshed != resource {
                    updatedResources[resourceIndex] = refreshed
                    changed = true
                }
            }
            if changed {
                messages[messageIndex].resources = updatedResources
            }
        }
    }

    // MARK: - Message Rating

    /// Rate a message (thumbs up/down)
    /// - Parameters:
    ///   - messageId: The message ID to rate
    ///   - rating: 1 for thumbs up, -1 for thumbs down, nil to clear rating
    func rateMessage(_ messageId: String, rating: Int?) async {
        // Update local state immediately for responsive UI
        if let index = messages.firstIndex(where: { $0.id == messageId }) {
            messages[index].rating = rating
        }

        // Persist to backend
        do {
            try await APIClient.shared.rateMessage(messageId: messageId, rating: rating)
            log("Rated message \(messageId) with rating: \(String(describing: rating))")

            // Track analytics
            if let rating = rating {
                AnalyticsManager.shared.messageRated(rating: rating)
            }
        } catch {
            logError("Failed to rate message", error: error)
            // Revert local state on failure
            if let index = messages.firstIndex(where: { $0.id == messageId }) {
                messages[index].rating = nil
            }
        }
    }

    // MARK: - ChatErrorState recovery dispatch

    /// User tapped the primary CTA on a `ChatErrorCard`. Dispatches to
    /// the matching recovery action and clears `currentError`.
    ///
    /// Every `ChatErrorRecoveryAction` case is wired to a concrete
    /// handler. Implementations are deliberately minimal: each one
    /// performs the smallest useful action that points the user at the
    /// fix path.
    ///
    /// - `.retry`: re-issue the last failed prompt.
    /// - `.dismiss`: clear without further action.
    /// - `.signIn`: open `https://omi.me/` so the user can complete
    ///   sign-in. Triggering native OAuth from a chat-error context
    ///   needs more UI plumbing than fits in this scope — surfacing
    ///   the URL is the honest minimum.
    /// - `.installRuntime`: open `https://nodejs.org/` so the user can
    ///   install Node before the bridge can spawn.
    func recoverFromError() async {
        guard let error = currentError else { return }
        let action = error.primaryRecovery
        let promptToRetry = lastFailedPrompt
        currentError = nil
        lastFailedPrompt = nil

        switch action {
        case .retry:
            if let prompt = promptToRetry, !prompt.isEmpty {
                if isSending {
                    if isStopping {
                        pendingErrorRecoveryPrompt = prompt
                        return
                    }
                    currentError = error
                    lastFailedPrompt = prompt
                    return
                }
                await sendMessage(prompt)
            }
        case .dismiss:
            break  // already cleared above
        case .signIn:
            log("ChatErrorCard: .signIn recovery — opening omi.me sign-in URL")
            if let url = URL(string: "https://omi.me/") {
                NSWorkspace.shared.open(url)
            }
        case .installRuntime:
            log("ChatErrorCard: .installRuntime recovery — opening nodejs.org for runtime install")
            if let url = URL(string: "https://nodejs.org/") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    /// User tapped the dismiss "x" on a `ChatErrorCard`. Clears the
    /// card without firing any recovery action. Used when the user
    /// wants to acknowledge the error and move on without retrying.
    func dismissCurrentError() {
        currentError = nil
        lastFailedPrompt = nil
    }

    // MARK: - Clear Chat

    /// Clear current session messages (delete and create new)
    func clearChat() async {
        isClearing = true
        defer { isClearing = false }

        if isInDefaultChat {
            // Default chat mode: clear UI immediately, delete in background
            let runtimeChatId = mainChatRuntimeChatId(sessionId: nil)
            let surface = AgentSurfaceReference.mainChat(chatId: runtimeChatId)
            messages = []
            resetMessagesPagination()
            AgentRuntimeStatusStore.shared.clear(surface: surface)
            await invalidateAgentSurface(surface: surface)
            log("Cleared default chat messages")
            Task {
                do {
                    _ = try await APIClient.shared.deleteMessages(appId: selectedAppId)
                } catch {
                    logError("Failed to clear default chat messages", error: error)
                }
            }
        } else {
            // Session mode: clear UI immediately, delete old session in background, create new
            let sessionToDelete = currentSession
            if let session = sessionToDelete {
                let surface = AgentSurfaceReference.mainChat(chatId: session.id)
                AgentRuntimeStatusStore.shared.clear(surface: surface)
                await invalidateAgentSurface(surface: surface)
            }

            // Immediately clear UI state
            if let session = sessionToDelete {
                sessions.removeAll { $0.id == session.id }
            }
            currentSession = nil
            messages = []
            resetMessagesPagination()

            // Delete old session in background (don't await — backend is slow)
            if let session = sessionToDelete {
                Task {
                    do {
                        try await APIClient.shared.deleteChatSession(sessionId: session.id)
                        log("Background deleted chat session: \(session.id)")
                    } catch {
                        logError("Failed to background delete chat session", error: error)
                    }
                }
            }

            // Create a fresh session immediately
            _ = await createNewSession()
        }

        log("Chat cleared")
        AnalyticsManager.shared.chatCleared()
    }

    // MARK: - App Selection

    /// Select a chat app and load its sessions
    func selectApp(_ appId: String?) async {
        guard selectedAppId != appId else { return }
        selectedAppId = appId
        currentSession = nil
        messages = []
        resetMessagesPagination()
        sessions = []
        errorMessage = nil
        isInDefaultChat = true

        if multiChatEnabled {
            // Multi-chat mode: load sessions, then switch to default chat
            await fetchSessions()
            await switchToDefaultChat()
        } else {
            // Single chat mode: just load default chat messages
            await loadDefaultChatMessages()
        }
    }

    // MARK: - Session Grouping Helpers

    /// Group sessions by date — called by the Combine observer, not on every SwiftUI render pass.
    private func computeGroupedSessions() -> [(String, [ChatSession])] {
        let calendar = Calendar.current
        let now = Date()

        var today: [ChatSession] = []
        var yesterday: [ChatSession] = []
        var thisWeek: [ChatSession] = []
        var older: [ChatSession] = []

        for session in filteredSessions {
            if calendar.isDateInToday(session.updatedAt) {
                today.append(session)
            } else if calendar.isDateInYesterday(session.updatedAt) {
                yesterday.append(session)
            } else if let weekAgo = calendar.date(byAdding: .day, value: -7, to: now),
                      session.updatedAt > weekAgo {
                thisWeek.append(session)
            } else {
                older.append(session)
            }
        }

        var groups: [(String, [ChatSession])] = []
        if !today.isEmpty { groups.append(("Today", today)) }
        if !yesterday.isEmpty { groups.append(("Yesterday", yesterday)) }
        if !thisWeek.isEmpty { groups.append(("This Week", thisWeek)) }
        if !older.isEmpty { groups.append(("Older", older)) }

        return groups
    }

    // MARK: - Local automation (continuity gauntlet)

  private static let automationAuthUserIdKey = "auth_userId"
  /// Owner A's real uid, stashed by automationSwapTestOwner so restore_test_owner can
  /// undo the swap. Without this the synthetic owner persists in UserDefaults across
  /// relaunches and every backend-auth path breaks (mint, kernel persist, goals).
  private static let automationOwnerABackupKey = "automation_swap_owner_a_backup"

  /// Test-bundle-only owner swap: clear kernel state for owner A, register synthetic
  /// owner B, and run one main-chat probe turn under a QueryTracer context.
  func automationSwapTestOwner(ownerBId: String, probeQuery: String) async -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "swap_test_owner is disabled on production bundles"]
    }
    let trimmedOwnerB = ownerBId.trimmingCharacters(in: .whitespacesAndNewlines)
    let trimmedQuery = probeQuery.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmedOwnerB.isEmpty else { return ["error": "missing 'owner_b'"] }
    guard !trimmedQuery.isEmpty else { return ["error": "missing 'query'"] }
    guard let ownerA = runtimeOwnerId, !ownerA.isEmpty else {
      return ["error": "owner A is not signed in"]
    }
    guard trimmedOwnerB != ownerA else {
      return ["error": "owner_b must differ from the active owner"]
    }

    _ = await ensureBridgeStarted()
    if agentBridgeStarted {
      await resolvedAgentClient().clearOwnerState()
    }

    UserDefaults.standard.set(ownerA, forKey: Self.automationOwnerABackupKey)
    UserDefaults.standard.set(trimmedOwnerB, forKey: Self.automationAuthUserIdKey)
    resetSessionStateForAuthChange()

    let tracer = QueryTracer(query: trimmedQuery, inputMode: .text)
    await QueryTracerContext.$current.withValue(tracer) {
      _ = await sendMessage(trimmedQuery)
    }

    var detail = automationMainChatSnapshot(limit: 20)
    detail["owner_a"] = ownerA
    detail["owner_b"] = trimmedOwnerB
    detail["probe_query"] = trimmedQuery
    return detail
  }

  /// Undo automationSwapTestOwner: restore the stashed real owner and reset session
  /// state. Safe no-op when no swap is active. Harnesses must call this after the
  /// owner suite (and may call it defensively pre-run).
  func automationRestoreTestOwner() async -> [String: String] {
    guard AppBuild.isNonProduction else {
      return ["error": "restore_test_owner is disabled on production bundles"]
    }
    let defaults = UserDefaults.standard
    guard let ownerA = defaults.string(forKey: Self.automationOwnerABackupKey),
          !ownerA.isEmpty
    else {
      return ["restored": "false", "note": "no owner swap active"]
    }

    _ = await ensureBridgeStarted()
    if agentBridgeStarted {
      await resolvedAgentClient().clearOwnerState()
    }

    defaults.set(ownerA, forKey: Self.automationAuthUserIdKey)
    defaults.removeObject(forKey: Self.automationOwnerABackupKey)
    resetSessionStateForAuthChange()
    return ["restored": "true", "owner_id": ownerA]
  }

    /// Snapshot for `main_chat_snapshot` / `wait_main_chat_idle` harness actions.
    func automationMainChatSnapshot(limit: Int) -> [String: String] {
        let boundedLimit = max(1, limit)
        let runtimeChatId = mainChatRuntimeChatId(sessionId: currentSessionId)
        let rows: [[String: String]] = messages.suffix(boundedLimit).map { message in
            [
                "id": message.id,
                "role": message.sender == .user ? "user" : "assistant",
                "text": message.copyableText,
                "streaming": message.isStreaming ? "true" : "false",
            ]
        }
        let messagesJSON: String
        if let data = try? JSONSerialization.data(withJSONObject: rows),
            let encoded = String(data: data, encoding: .utf8)
        {
            messagesJSON = encoded
        } else {
            messagesJSON = "[]"
        }
        var detail: [String: String] = [
            "chat_session_id": currentSessionId ?? "",
            "runtime_chat_id": runtimeChatId,
            "is_sending": isSending ? "true" : "false",
            "is_streaming": messages.contains(where: { $0.isStreaming }) ? "true" : "false",
            "message_count": "\(messages.count)",
            "messages_json": messagesJSON,
        ]
        if let lastAssistant = messages.last(where: { $0.sender != .user })?.copyableText {
            detail["last_assistant_text"] = lastAssistant
        }
        if let ownerId = runtimeOwnerId {
            detail["owner_id"] = ownerId
        }
        return detail
    }

    /// Clear kernel `main_chat` turns for the active owner (continuity harness hygiene).
    func automationClearOwnerSurfaceState(chatId: String = "default") async -> [String: String] {
        guard AppBuild.isNonProduction else {
            return ["error": "clear_owner_surface_state is disabled on production bundles"]
        }
        _ = await ensureBridgeStartedForKernel()
        await kernelTurnProjection.clearOwnerSurfaceState(chatId: chatId)
        return ["cleared": "true", "chat_id": chatId]
    }

    /// Read-only kernel `main_chat` turn tail for continuity harness evidence.
    func automationKernelTurnTail(limit: Int = 8) async -> [String: String] {
        let boundedLimit = max(1, limit)
        guard await ensureBridgeStartedForKernel(),
              let tail = await kernelTurnProjection.fetchKernelTurnTail(limit: boundedLimit)
        else {
            return ["error": "kernel turn tail unavailable"]
        }
        let rows: [[String: String]] = tail.turns.map { turn in
            [
                "role": turn.role,
                "content": turn.content,
                "surface_kind": turn.surfaceKind,
                "created_at_ms": "\(turn.createdAtMs)",
                "origin": turn.origin,
            ]
        }
        let turnsJSON: String
        if let data = try? JSONSerialization.data(withJSONObject: rows),
           let encoded = String(data: data, encoding: .utf8) {
            turnsJSON = encoded
        } else {
            turnsJSON = "[]"
        }
        return [
            "conversation_id": tail.conversationId,
            "turn_count": "\(tail.turns.count)",
            "turns_json": turnsJSON,
        ]
    }
}
