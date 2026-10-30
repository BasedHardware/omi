import Foundation

/// One structured part of an answer (backend `Message.content_blocks`, the vocabulary of the macOS
/// agent's `ConversationContentBlock`): a task, a link to a goal, memory or conversation, a
/// discovery, a question with prepared answers, a background run, or the day's memories to review.
/// Every block keeps the line a client that cannot draw it shows instead (`fallbackText`).
public struct ChatBlock: Identifiable, Hashable, Sendable {
    public let id: String
    public let kind: Kind
    /// The block as one line of text (the desktop's synthesized fallback); empty for blocks that
    /// say nothing on their own (a review card draws its own heading).
    public let fallbackText: String

    public enum Kind: Hashable, Sendable {
        /// Prose that belongs to the answer.
        case text(String)
        /// A task by id, drawn live from the task list.
        case task(taskID: String)
        case goal(goalID: String, summary: String)
        case memory(memoryID: String, summary: String)
        /// A conversation (`conversationLink`) or the capture an answer came from (`captureLink`).
        case conversation(conversationID: String, summary: String, actionItems: [ActionItemHint], isCapture: Bool)
        case discovery(title: String, summary: String, fullText: String)
        case question(ChatQuestion)
        /// A background run that started (`agentSpawn`) or ended (`agentCompletion`).
        case agentRun(title: String, detail: String, status: AgentRunStatus)
        /// "Things I learned today": memories to confirm, drop or correct (`memoryReviewCard`).
        case memoryReview(ChatMemoryReview)
        /// Thinking, a tool call, a citation, a malformed or unknown block: only its fallback line.
        case other(type: String)
    }

    /// An action item a conversation link recommends (plain text; the task exists when `taskID` is set).
    public struct ActionItemHint: Hashable, Sendable {
        public let description: String
        public let taskID: String?

        public init(description: String, taskID: String?) {
            self.description = description
            self.taskID = taskID
        }
    }

    public enum AgentRunStatus: Hashable, Sendable {
        case running, completed, cancelled, timedOut, failed

        /// Only explicit successful states read as completed; anything unknown reads as failed.
        public init(completionStatus raw: String) {
            switch raw.trimmingCharacters(in: .whitespaces).lowercased() {
            case "completed", "succeeded", "success": self = .completed
            case "cancelled", "canceled", "stopped": self = .cancelled
            case "timed_out", "timedout", "timeout": self = .timedOut
            default: self = .failed
            }
        }
    }

    public init(id: String, kind: Kind, fallbackText: String) {
        self.id = id
        self.kind = kind
        self.fallbackText = fallbackText
    }
}

/// A question Omi asks with answers ready to tap (`questionCard`). An answered one keeps the
/// question readable and shows only the chosen answer.
public struct ChatQuestion: Hashable, Sendable {
    public struct Option: Hashable, Sendable {
        public let id: String
        public let label: String
        /// What is sent when it is tapped (the label when the block has none).
        public let preparedAnswer: String

        public init(id: String, label: String, preparedAnswer: String) {
            self.id = id
            self.label = label
            self.preparedAnswer = preparedAnswer
        }
    }

    public let questionID: String
    public let text: String
    public let options: [Option]
    public let selectedOptionID: String?

    public init(questionID: String, text: String, options: [Option], selectedOptionID: String?) {
        self.questionID = questionID
        self.text = text
        self.options = options
        self.selectedOptionID = selectedOptionID
    }

    /// The answers to show: all of them, or only the chosen one once answered.
    public var visibleOptions: [Option] {
        guard let selectedOptionID else { return options }
        return options.filter { $0.id == selectedOptionID }
    }

    public var isAnswered: Bool {
        selectedOptionID != nil
    }
}

/// Up to three memories the day produced, by id and the text the recap showed
/// (`backend/utils/memory/learned_today.py`). The verdicts live on the memories themselves.
public struct ChatMemoryReview: Hashable, Sendable {
    public struct Item: Hashable, Sendable, Identifiable {
        public let memoryID: String
        public let content: String
        public let category: String

        public var id: String {
            memoryID
        }

        public init(memoryID: String, content: String, category: String) {
            self.memoryID = memoryID
            self.content = content
            self.category = category
        }
    }

    /// The card never shows more than this many rows.
    public static let maxItems = 3

    public let summaryID: String
    /// The recap's local day (`yyyy-MM-dd`).
    public let date: String
    public let items: [Item]

    public init(summaryID: String, date: String, items: [Item]) {
        self.summaryID = summaryID
        self.date = date
        self.items = Array(items.prefix(Self.maxItems))
    }
}
