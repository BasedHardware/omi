import Foundation
import OmiCore

/// One thing the app puts in Spotlight: a title, a short text and where a tap goes. Only what the
/// user already sees in the lists; no transcripts.
public struct SpotlightRecord: Hashable, Sendable {
    public enum Kind: String, CaseIterable, Sendable {
        case conversation, task, memory
    }

    public let kind: Kind
    public let id: String
    public let title: String
    public let text: String
    public let date: Date?

    /// The item's stable identifier in the index, and what a tap on it opens.
    public var link: DeepLink {
        switch kind {
        case .conversation: .conversation(id: id)
        case .task: .task(id: id)
        case .memory: .memory(id: id)
        }
    }

    public var identifier: String {
        link.url.absoluteString
    }

    /// Short texts keep the index small and never carry a whole memory or overview.
    public static let textLimit = 300
    /// The newest of each kind; Spotlight is for finding recent things again.
    public static let perKindLimit = 200

    public init(kind: Kind, id: String, title: String, text: String, date: Date?) {
        self.kind = kind
        self.id = id
        self.title = title
        self.text = String(text.prefix(Self.textLimit))
        self.date = date
    }

    /// Finished conversations (not ones still processing or that failed), the user's own tasks and
    /// every memory.
    public static func records(conversations: [Conversation], tasks: [ActionItem], memories: [Memory]) -> [SpotlightRecord] {
        let finished = conversations.filter { $0.status == .completed && !$0.title.isEmpty }.prefix(perKindLimit).map {
            SpotlightRecord(kind: .conversation, id: $0.id, title: $0.title, text: $0.overview, date: $0.date)
        }
        let mine = tasks.filter { $0.owner != .other }.prefix(perKindLimit).map {
            SpotlightRecord(kind: .task, id: $0.id, title: $0.description, text: "", date: $0.dueAt ?? $0.createdAt)
        }
        let known = memories.prefix(perKindLimit).map {
            SpotlightRecord(kind: .memory, id: $0.id, title: memoryTitle($0), text: $0.content, date: $0.createdAt)
        }
        return finished + mine + known
    }

    /// A memory's headline, or its first words.
    public static func memoryTitle(_ memory: Memory) -> String {
        if let headline = memory.headline?.trimmingCharacters(in: .whitespacesAndNewlines), !headline.isEmpty { return headline }
        let content = memory.content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard content.count > 60 else { return content }
        let head = content.prefix(60)
        return String(head.lastIndex(where: \.isWhitespace).map { head[..<$0] } ?? head) + "…"
    }
}
