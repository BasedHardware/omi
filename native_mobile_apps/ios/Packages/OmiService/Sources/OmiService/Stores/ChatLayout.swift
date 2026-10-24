import Foundation
import OmiCore

/// How the thread lays out, as in Messages. Pure rules, so they are tested without a screen:
/// long answers in a few bubbles, bubbles of one sender grouped, which extras an answer shows,
/// cards of a kind stacked, whether the list sits at its end, and when the app header collapses.

/// A long answer in a few bubbles: split where a paragraph ends (a blank line), never inside
/// fenced code, a list, a table or a quote, a heading or a line ending in ":" kept with what it
/// introduces. At most `maxBubbles`; the rest stays in the last one. While an answer streams,
/// finished paragraphs keep their bubbles: only the end grows (a loose list joins its items).
public enum ChatBubbleSplit {
    public static let maxBubbles = 4

    public static func split(_ text: String) -> [String] {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }
        var chunks: [[String]] = []
        var current: [String] = []
        var insideFence = false
        for line in trimmed.components(separatedBy: "\n") {
            let bare = line.trimmingCharacters(in: .whitespaces)
            if bare.hasPrefix("```") { insideFence.toggle() }
            if bare.isEmpty, !insideFence {
                if !current.isEmpty { chunks.append(current) }
                current = []
            } else {
                current.append(line)
            }
        }
        if !current.isEmpty { chunks.append(current) }

        var merged: [[String]] = []
        for chunk in chunks {
            if let previous = merged.last, belongTogether(previous, chunk) {
                merged[merged.count - 1] = previous + [""] + chunk
            } else {
                merged.append(chunk)
            }
        }
        var texts = merged.map { $0.joined(separator: "\n") }
        if texts.count > maxBubbles {
            let rest = texts[(maxBubbles - 1)...].joined(separator: "\n\n")
            texts = Array(texts.prefix(maxBubbles - 1)) + [rest]
        }
        return texts
    }

    /// Two paragraphs that read as one: a heading or an intro ("Here is what I found:") and what
    /// follows, a list or table or quote that goes on (loose list items), or an indented line.
    static func belongTogether(_ first: [String], _ second: [String]) -> Bool {
        guard let last = first.last?.trimmingCharacters(in: .whitespaces),
              let next = second.first else { return false }
        let nextBare = next.trimmingCharacters(in: .whitespaces)
        if first.allSatisfy({ $0.trimmingCharacters(in: .whitespaces).hasPrefix("#") }) { return true }
        if last.hasSuffix(":") { return true }
        if isListItem(last), isListItem(nextBare) || next.hasPrefix("  ") { return true }
        if last.hasPrefix("|"), nextBare.hasPrefix("|") { return true }
        if last.hasPrefix(">"), nextBare.hasPrefix(">") { return true }
        // An unclosed fence: the code goes on in the next part.
        let fences = first.count { $0.trimmingCharacters(in: .whitespaces).hasPrefix("```") }
        return fences % 2 == 1
    }

    static func isListItem(_ line: String) -> Bool {
        line.wholeMatch(of: /[*\-•+–◦]\s+.+/) != nil || line.wholeMatch(of: /\d{1,3}[.)]\s+.+/) != nil
    }
}

/// Bubbles of one sender in a row form a group (a few points apart; more room between groups):
/// only its last bubble carries the tail, and Omi's avatar sits beside it.
public enum ChatGrouping {
    /// One row of the thread. `sender` nil: not a message (a day line, a finished run), which
    /// always ends a group.
    public struct Item: Sendable {
        public let id: String
        public let sender: ChatMessage.Sender?
        public let date: Date?
        /// Something stands above its bubbles (steps, cards): it starts a new group.
        public let leadsWithExtras: Bool
        /// Something stands below its bubbles (sources, a follow-up): the group ends with it.
        public let endsWithExtras: Bool

        public init(
            id: String, sender: ChatMessage.Sender?, date: Date? = nil, leadsWithExtras: Bool = false, endsWithExtras: Bool = false
        ) {
            self.id = id
            self.sender = sender
            self.date = date
            self.leadsWithExtras = leadsWithExtras
            self.endsWithExtras = endsWithExtras
        }
    }

    public struct Position: Hashable, Sendable {
        public let isFirst: Bool
        public let isLast: Bool

        public init(isFirst: Bool, isLast: Bool) {
            self.isFirst = isFirst
            self.isLast = isLast
        }

        public static let alone = Position(isFirst: true, isLast: true)
    }

    /// Messages further apart than this start a new group.
    public static let maxGap: TimeInterval = 10 * 60

    public static func positions(_ items: [Item]) -> [String: Position] {
        var result: [String: Position] = [:]
        for (index, item) in items.enumerated() where item.sender != nil {
            let joinsPrevious = index > 0 && joined(items[index - 1], item)
            let joinsNext = index + 1 < items.count && joined(item, items[index + 1])
            result[item.id] = Position(isFirst: !joinsPrevious, isLast: !joinsNext)
        }
        return result
    }

    static func joined(_ first: Item, _ second: Item) -> Bool {
        guard let sender = first.sender, sender == second.sender, !first.endsWithExtras, !second.leadsWithExtras else { return false }
        guard let start = first.date, let end = second.date else { return true }
        return abs(end.timeIntervalSince(start)) <= maxGap
    }
}

/// What shows under an answer. Only the newest answer keeps its source chips and its follow-up
/// question (the follow-up only while nothing is typed); an older one folds its sources into a
/// small "2 sources" line that opens them. "Stop reading" only while that answer is read aloud.
public enum ChatAnswerExtras {
    public enum Sources: Equatable, Sendable {
        case none
        case chips
        case collapsed(Int)
    }

    public struct Shown: Equatable, Sendable {
        public let sources: Sources
        public let followUp: Bool
        public let stopReading: Bool

        public init(sources: Sources, followUp: Bool, stopReading: Bool) {
            self.sources = sources
            self.followUp = followUp
            self.stopReading = stopReading
        }

        /// Anything at all below the bubbles.
        public var isEmpty: Bool {
            sources == .none && !followUp && !stopReading
        }
    }

    /// The answer itself: the newest one, still streaming, failed (no reply came), how many
    /// conversations it drew on, whether it has a follow-up question.
    public struct Answer: Equatable, Sendable {
        public let isLatest: Bool
        public let isStreaming: Bool
        public let failed: Bool
        public let citations: Int
        public let hasFollowUp: Bool

        public init(isLatest: Bool, isStreaming: Bool = false, failed: Bool = false, citations: Int = 0, hasFollowUp: Bool = false) {
            self.isLatest = isLatest
            self.isStreaming = isStreaming
            self.failed = failed
            self.citations = citations
            self.hasFollowUp = hasFollowUp
        }
    }

    public static func shown(_ answer: Answer, draftIsEmpty: Bool, isSpeaking: Bool, sourcesExpanded: Bool = false) -> Shown {
        let sources: Sources = if answer.failed || answer.citations == 0 {
            .none
        } else if answer.isLatest || sourcesExpanded {
            .chips
        } else {
            .collapsed(answer.citations)
        }
        return Shown(
            sources: sources,
            followUp: answer.isLatest && !answer.isStreaming && !answer.failed && answer.hasFollowUp && draftIsEmpty,
            stopReading: isSpeaking
        )
    }
}

/// Never two cards of one kind in a row: a run of them becomes one stack (the first card and
/// "n more").
public enum ChatStacking {
    public static func stacks<Item>(_ items: [Item], kind: (Item) -> String) -> [[Item]] {
        var result: [[Item]] = []
        var lastKind: String?
        for item in items {
            let itemKind = kind(item)
            if itemKind == lastKind, !result.isEmpty {
                result[result.count - 1].append(item)
            } else {
                result.append([item])
            }
            lastKind = itemKind
        }
        return result
    }
}

public extension ChatCard {
    /// Cards of one kind stack (two connections, three new tasks).
    var kind: String {
        switch self {
        case .connect: "connect"
        case .taskAdded: "added"
        case .taskCompleted: "done"
        }
    }
}

/// Whether the thread rests at its end, for following new words and the jump-to-latest button.
/// The geometry is believed as soon as it says "at the end"; it only says "not at the end" while
/// the user scrolls (an answer growing or the keyboard coming up never stops the following),
/// and once a scroll comes to rest wherever it ended (also a fling that bounced at the end).
public struct ChatBottomTracker: Equatable, Sendable {
    /// How close to the end still counts as at the end (a line or two of a bubble).
    public static let threshold: Double = 80

    public private(set) var isAtBottom = true
    public private(set) var geometryAtBottom = true
    public private(set) var isScrolling = false

    public init() {}

    /// At the end while the content's end is within `threshold` of the visible bottom edge
    /// (above the composer and keyboard, which `bottomInset` covers).
    public static func isAtBottom(
        offsetY: Double, containerHeight: Double, bottomInset: Double, contentHeight: Double, threshold: Double = threshold
    ) -> Bool {
        offsetY + containerHeight - bottomInset >= contentHeight - threshold
    }

    public mutating func geometryChanged(atBottom: Bool) {
        geometryAtBottom = atBottom
        if atBottom || isScrolling { isAtBottom = atBottom }
    }

    public mutating func phaseChanged(isIdle: Bool) {
        isScrolling = !isIdle
        if isIdle { isAtBottom = geometryAtBottom }
    }

    /// The jump button or a sent question took the list to its end.
    public mutating func jumpedToBottom() {
        isAtBottom = true
        geometryAtBottom = true
    }
}
