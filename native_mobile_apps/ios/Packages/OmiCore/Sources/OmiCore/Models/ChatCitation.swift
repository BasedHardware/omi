import Foundation

/// A source chip under an answer ("Q4 roadmap · 14:05"): a conversation the answer drew on, at the
/// moment it came from when the backend said which (evidence), else at its start.
public struct ChatCitation: Identifiable, Hashable, Sendable {
    public let conversationID: String
    public let title: String
    public let emoji: String?
    /// When it was said: the conversation's start plus the moment's offset (nil when unknown).
    public let time: Date?
    /// Seconds from the conversation's start, for opening it at that moment.
    public let offset: TimeInterval?

    public var id: String {
        "\(conversationID)|\(offset.map { String(Int($0)) } ?? "")"
    }

    public init(conversationID: String, title: String, emoji: String?, time: Date?, offset: TimeInterval?) {
        self.conversationID = conversationID
        self.title = title
        self.emoji = emoji
        self.time = time
        self.offset = offset
    }
}

public extension ChatMessage {
    /// Every conversation the answer cites, once per moment: evidence first (it knows the moment),
    /// then the referenced conversations evidence did not cover. At most `limit`.
    func citations(limit: Int = 6) -> [ChatCitation] {
        var result: [ChatCitation] = []
        var seen = Set<String>()
        var covered = Set<String>()
        let byID = Dictionary(references.map { ($0.conversationID, $0) }, uniquingKeysWith: { first, _ in first })
        for item in evidence where item.opensConversation {
            guard let id = item.conversationID else { continue }
            let reference = byID[id]
            let offset = item.kind == .conversationSegment ? item.startMs.map { TimeInterval($0) / 1000 } : nil
            let citation = ChatCitation(
                conversationID: id,
                title: reference.flatMap { $0.title.isEmpty ? nil : $0.title } ?? item.title ?? "",
                emoji: reference?.emoji,
                time: reference?.createdAt.map { $0.addingTimeInterval(offset ?? 0) },
                offset: offset
            )
            covered.insert(id)
            if seen.insert(citation.id).inserted { result.append(citation) }
        }
        for reference in references where !covered.contains(reference.conversationID) {
            let citation = ChatCitation(
                conversationID: reference.conversationID, title: reference.title, emoji: reference.emoji,
                time: reference.createdAt, offset: nil
            )
            if seen.insert(citation.id).inserted { result.append(citation) }
        }
        return Array(result.prefix(limit))
    }
}
