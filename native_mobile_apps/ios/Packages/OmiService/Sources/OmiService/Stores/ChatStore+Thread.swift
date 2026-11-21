import Foundation
import OmiCore

/// Finding things in the one long thread: a search over the loaded history and filter chips.
public enum ChatThreadFilter: String, CaseIterable, Sendable {
    /// Omi asked before acting (a message to send, a contact, a permission).
    case approvals
    /// Answers that prepared something for the user to send or use.
    case drafts
    /// Hand-overs and what Omi did to tasks.
    case jobs
    /// Photos and files sent in the chat.
    case files
}

public extension ChatStore {
    /// Words that mark an answer as carrying a draft.
    internal static let draftWords = ["draft", "entwurf", "entworfen"]
    /// Words that mark an answer as work on tasks.
    internal static let taskWords = ["task", "to-do", "todo", "aufgabe"]

    /// Whether `message` belongs in the thread under `query` and `filter` (nil: everything).
    func matches(_ message: ChatMessage, query: String, filter: ChatThreadFilter?) -> Bool {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        if !query.isEmpty {
            let inText = message.text.localizedStandardContains(query)
            let inFiles = message.files.contains { $0.name.localizedStandardContains(query) }
            let inSources = message.references.contains { $0.title.localizedStandardContains(query) }
            guard inText || inFiles || inSources else { return false }
        }
        guard let filter else { return true }
        switch filter {
        case .approvals:
            return askedMessageIDs.contains(message.id)
        case .drafts:
            guard message.sender == .omi, message.failure == nil else { return false }
            let text = message.text.lowercased()
            return Self.draftWords.contains { text.contains($0) }
                || (askedMessageIDs.contains(message.id) && message.steps.contains { $0.lowercased().contains("draft") })
        case .jobs:
            let touched = ChatCardDetector.touchedTasks(steps: message.steps)
            let hasTaskCard = cards(for: message.id).contains { if case .connect = $0 { false } else { true } }
            // Stored answers carry no steps: one that talks about a task it set or finished counts too.
            let text = message.text.lowercased()
            let aboutTasks = Self.taskWords.contains { text.contains($0) }
            return message.sender == .omi && message.failure == nil && (touched || hasTaskCard || aboutTasks)
        case .files:
            return !message.files.isEmpty
        }
    }

    /// The loaded messages that match (all of them without a query or filter).
    func visibleMessages(query: String, filter: ChatThreadFilter?) -> [ChatMessage] {
        let query = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty || filter != nil else { return messages }
        return messages.filter { matches($0, query: query, filter: filter) }
    }
}

/// The long-press menu of a message: delete on this iPhone, try a failed question again.
public extension ChatStore {
    /// Removes `messageID` from the thread on this iPhone; the backend keeps it. It stays hidden
    /// when the history loads again. Not while its answer is still coming in.
    func hide(_ messageID: String) {
        guard let index = messages.firstIndex(where: { $0.id == messageID }) else { return }
        let message = messages[index]
        if isStreaming, message.id == messages.last?.id { return }
        let stored = Set([message.id, message.serverID].compactMap(\.self))
            .filter { !$0.hasPrefix("local-") && !$0.hasPrefix("pending-") }
        for id in stored.sorted() {
            preferences.append(id, to: .hiddenChatMessages)
        }
        messages.remove(at: index)
        if replyingTo?.id == messageID { replyingTo = nil }
    }

    /// The failed answer right after the question `messageID` (its "Try again" asks it once more).
    func failedAnswer(after messageID: String) -> ChatMessage? {
        guard let index = messages.firstIndex(where: { $0.id == messageID }), messages[index].sender == .user,
              index + 1 < messages.count else { return nil }
        let answer = messages[index + 1]
        guard answer.sender == .omi, !(isStreaming && answer.id == messages.last?.id) else { return nil }
        switch answer.failure {
        case .couldNotAnswer, .offline, .timeout: return answer
        case .interrupted, .stopped, .quotaExceeded: return nil
        case nil: return answer.isServiceFailure ? answer : nil
        }
    }
}

/// How the thread names a day in its dividers: "Today", "Yesterday", a weekday within the last
/// week, otherwise the date.
public enum ChatDay: Hashable, Sendable {
    case today
    case yesterday
    case weekday(Date)
    case date(Date, showsYear: Bool)

    public init(_ date: Date, now: Date = .now, calendar: Calendar = .current) {
        let day = calendar.startOfDay(for: date)
        let today = calendar.startOfDay(for: now)
        let days = calendar.dateComponents([.day], from: day, to: today).day ?? 0
        switch days {
        case 0: self = .today
        case 1: self = .yesterday
        case 2 ..< 7: self = .weekday(day)
        default: self = .date(day, showsYear: !calendar.isDate(day, equalTo: today, toGranularity: .year))
        }
    }
}
