import Foundation
import OmiCore

/// `content_blocks` of a chat message (backend `models/chat.py` stores them verbatim; the
/// vocabulary is the macOS agent's `ConversationContentBlock`, mirrored by Flutter's
/// `chat_content_block.dart`). Two dialects arrive: camelCase (desktop, agent runs) and snake_case
/// (chat-first specs), so every field is read in both. A push carries the array as a JSON string.
/// A malformed block keeps its fallback line as `.other`; the follow-up and evidence blocks are
/// read elsewhere and left out.
enum ChatBlockMapper {
    static func blocks(from value: Any?) -> [ChatBlock] {
        let raw: [[String: Any]]
        if let array = value as? [[String: Any]] {
            raw = array
        } else if let text = value as? String, let data = text.data(using: .utf8),
                  let array = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        {
            raw = array
        } else {
            return []
        }
        return raw.enumerated().compactMap { index, object in block(from: object, index: index) }
    }

    /// Types that never become a block: the follow-up chip and the evidence envelope.
    static let skippedTypes: Set = ["followUp", "follow_up", "evidence", "evidence_envelope"]

    static func block(from object: [String: Any], index: Int = 0) -> ChatBlock? {
        guard let type = string(object, "type"), !skippedTypes.contains(type) else { return nil }
        let fallback = fallbackText(object)
        let id = string(object, "id") ?? "block-\(index)"
        let kind = string(object, "id") == nil ? nil : kind(type, object)
        guard let kind else {
            // Malformed: only its line, and nothing at all when the line is empty.
            return fallback.isEmpty ? nil : ChatBlock(id: id, kind: .other(type: type), fallbackText: fallback)
        }
        return ChatBlock(id: id, kind: kind, fallbackText: fallback)
    }

    private static func kind(_ type: String, _ object: [String: Any]) -> ChatBlock.Kind? {
        switch type {
        case "text":
            return .text(string(object, "text") ?? "")
        case "taskCard", "task_card":
            return string(object, "taskId", "task_id").map { .task(taskID: $0) }
        case "goalLink", "goal_link":
            guard let goal = string(object, "goalId", "goal_id"), let summary = string(object, "summary") else { return nil }
            return .goal(goalID: goal, summary: summary)
        case "memoryLink", "memory_link":
            guard let memory = string(object, "memoryId", "memory_id"), let summary = string(object, "summary") else { return nil }
            return .memory(memoryID: memory, summary: summary)
        case "conversationLink", "conversation_link", "captureLink", "capture_link":
            guard let conversation = string(object, "conversationId", "conversation_id"), let summary = string(object, "summary") else {
                return nil
            }
            let items = (object["recommendedActionItems"] ?? object["recommended_action_items"]) as? [[String: Any]] ?? []
            let hints = items.compactMap { item in
                string(item, "description").map { ChatBlock.ActionItemHint(description: $0, taskID: string(item, "taskId", "task_id")) }
            }
            return .conversation(
                conversationID: conversation, summary: summary, actionItems: hints, isCapture: type.hasPrefix("capture")
            )
        case "discoveryCard", "discovery_card":
            return .discovery(
                title: string(object, "title") ?? "", summary: string(object, "summary") ?? "",
                fullText: string(object, "fullText", "full_text") ?? ""
            )
        case "questionCard", "question_card":
            return question(object).map(ChatBlock.Kind.question)
        case "agentSpawn", "agent_spawn":
            guard string(object, "sessionId", "session_id") != nil, string(object, "runId", "run_id") != nil else { return nil }
            return .agentRun(title: string(object, "title") ?? "", detail: string(object, "objective") ?? "", status: .running)
        case "agentCompletion", "agent_completion":
            // Older stored completions carry no status: they were completed.
            let status = ChatBlock.AgentRunStatus(completionStatus: string(object, "status") ?? "completed")
            return .agentRun(title: string(object, "title") ?? "", detail: string(object, "output") ?? "", status: status)
        case "memoryReviewCard", "memory_review_card":
            return memoryReview(object).map(ChatBlock.Kind.memoryReview)
        default:
            return .other(type: type)
        }
    }

    /// Needs the question, its subject and at least one option with an id and a label.
    private static func question(_ object: [String: Any]) -> ChatQuestion? {
        guard let questionID = string(object, "questionId", "question_id"), let text = string(object, "text"),
              let subject = object["subject"] as? [String: Any], string(subject, "kind") != nil, string(subject, "id") != nil,
              let rawOptions = object["options"] as? [[String: Any]] else { return nil }
        let options = rawOptions.compactMap { option -> ChatQuestion.Option? in
            guard let id = string(option, "optionId", "option_id"), let label = string(option, "label") else { return nil }
            return ChatQuestion.Option(id: id, label: label, preparedAnswer: string(option, "preparedAnswer", "prepared_answer") ?? label)
        }
        guard !options.isEmpty else { return nil }
        return ChatQuestion(
            questionID: questionID, text: text, options: options,
            selectedOptionID: string(object, "selectedOptionId", "selected_option_id")
        )
    }

    /// Items without an id or text are dropped; a card with none left is no card.
    private static func memoryReview(_ object: [String: Any]) -> ChatMemoryReview? {
        let items = (object["items"] as? [[String: Any]] ?? []).compactMap { item -> ChatMemoryReview.Item? in
            guard let id = string(item, "memoryId", "memory_id"), let content = string(item, "content") else { return nil }
            return ChatMemoryReview.Item(memoryID: id, content: content, category: string(item, "category") ?? "")
        }
        guard !items.isEmpty else { return nil }
        return ChatMemoryReview(
            summaryID: string(object, "summaryId", "summary_id") ?? "", date: string(object, "date") ?? "", items: items
        )
    }

    /// The one line a block reads as without its card (Flutter `ServerMessage._blockFallbackText`,
    /// which follows the desktop's projection), so a turn whose text is only these lines can show
    /// the cards instead of repeating them.
    static func fallbackText(_ object: [String: Any]) -> String {
        func value(_ camel: String, _ snake: String? = nil) -> String {
            string(object, camel, snake)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        }
        func labelled(_ label: String, _ details: [String]) -> String {
            var unique: [String] = []
            for detail in details where !detail.isEmpty && !unique.contains(detail) {
                unique.append(detail)
            }
            return unique.isEmpty ? label : ([label] + unique).joined(separator: " - ")
        }
        switch string(object, "type") ?? "" {
        case "text": return value("text").isEmpty ? "Message" : value("text")
        case "toolCall", "tool_call": return labelled("Tool", [value("name"), value("output"), value("inputSummary", "input_summary")])
        case "thinking": return labelled("Thinking", [value("text")])
        case "discoveryCard", "discovery_card": return labelled("Discovery", [value("title"), value("summary")])
        case "questionCard", "question_card": return value("text").isEmpty ? "Question" : value("text")
        case "memoryReviewCard", "memory_review_card", "followUp", "follow_up", "evidence", "evidence_envelope": return ""
        case "taskCard", "task_card": return "Task"
        case "goalLink", "goal_link": return labelled("Goal", [value("summary")])
        case "captureLink", "capture_link": return labelled("Capture", [value("summary")])
        case "conversationLink", "conversation_link": return labelled("Meeting notes ready", [value("summary")])
        case "memoryLink", "memory_link": return labelled("Memory", [value("summary")])
        case "citation": return labelled("Source", [value("title"), value("preview")])
        case "agentSpawn", "agent_spawn": return labelled("Agent started", [value("title"), value("objective")])
        case "agentCompletion", "agent_completion": return labelled("Agent completed", [value("title"), value("output")])
        default: return labelled("Chat item", [value("title"), value("summary"), value("text")])
        }
    }

    /// A non-blank string under the camelCase key, else the snake_case one.
    private static func string(_ object: [String: Any], _ camel: String, _ snake: String? = nil) -> String? {
        let value = object[camel] ?? snake.flatMap { object[$0] }
        guard let text = value as? String, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }
}
