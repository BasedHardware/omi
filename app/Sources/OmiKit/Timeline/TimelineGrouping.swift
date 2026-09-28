import Foundation

// Port of the grouping half of `react-native/src/desktop/timeline/UnifiedTimeline.tsx`:
// Date / Type / Topic sections with the same ordering and labels. Deterministic:
// "now" and the calendar (for day bucketing) are injected; date formatting is
// locale-independent (en_US_POSIX), unlike the TS `toLocaleDateString` calls.

public struct TimelineSection: Sendable, Hashable {
    public var key: String
    public var label: String
    public var entries: [TimelineEntry]

    public init(key: String, label: String, entries: [TimelineEntry]) {
        self.key = key
        self.label = label
        self.entries = entries
    }
}

// MARK: - Date labels

/// Port of `dayLabel`: Today / Yesterday / "Weekday, Month Day" for older
/// entries, "Undated" for atMs == 0. Day buckets follow the injected
/// calendar's time zone (the TS used the device's local midnight).
public func timelineDayLabel(
    atMs: Int64,
    nowMs: Int64,
    calendar: Calendar = Calendar.current
) -> String {
    if atMs == 0 { return "Undated" }
    var dayCalendar = calendar
    dayCalendar.timeZone = calendar.timeZone
    func startOfDay(_ ms: Int64) -> Int64 {
        let date = Date(timeIntervalSince1970: Double(ms) / 1000.0)
        let start = dayCalendar.startOfDay(for: date)
        return Int64(start.timeIntervalSince1970 * 1000)
    }
    // TS used Math.round over the millisecond difference, so DST-shortened
    // days still count as one day.
    let days = Int((Double(startOfDay(nowMs) - startOfDay(atMs)) / 86_400_000.0).rounded())
    if days <= 0 { return "Today" }
    if days == 1 { return "Yesterday" }
    // Locale-independent "Weekday, Month Day" (TS: toLocaleDateString with
    // weekday: 'long', month: 'long', day: 'numeric').
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = calendar.timeZone
    formatter.dateFormat = "EEEE, MMMM d"
    return formatter.string(from: Date(timeIntervalSince1970: Double(atMs) / 1000.0))
}

/// Port of `timeLabel` — locale-independent "h:mm a".
public func timelineTimeLabel(atMs: Int64) -> String {
    if atMs == 0 { return "" }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(identifier: "UTC")
    formatter.dateFormat = "h:mm a"
    return formatter.string(from: Date(timeIntervalSince1970: Double(atMs) / 1000.0))
}

// MARK: - Topic tokens

/// `TOPIC_STOPWORDS` from UnifiedTimeline.tsx.
let timelineTopicStopwords: Set<String> = [
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "are",
    "was", "were", "will", "your", "about", "into", "over", "after", "before",
    "what", "when", "they", "them", "their", "there", "where", "which", "while",
    "would", "could", "should", "been", "being", "does", "done", "just", "like",
    "some", "more", "than", "then", "because", "also", "very", "much", "many",
    "most", "other", "such", "only", "both", "each", "once", "here", "how",
    "who", "whom", "its", "our", "you", "she", "him", "her", "his", "says",
    "said", "new", "now", "one", "two", "all", "can", "get", "got", "make",
    "made", "out", "up", "down", "not", "but", "yet", "off", "own", "same",
    "so", "too", "sobre", "via", "using", "used", "use",
]

let otherTopicLabel = "Everything else"

/// Port of `topicTokens`: `[a-z][a-z0-9+#]*` matches over the lowercased
/// "title detail" haystack, dropping tokens shorter than 4 characters,
/// stopwords, and duplicates. Byte-level scan (no Character APIs).
func topicTokens(_ entry: TimelineEntry) -> [String] {
    let haystack = "\(entry.title) \(entry.detail)".lowercased()
    let bytes = Array(haystack.utf8)
    var tokens: [String] = []
    var seen = Set<String>()
    var index = 0
    func isWordStart(_ byte: UInt8) -> Bool { byte >= 97 && byte <= 122 }
    func isWordBody(_ byte: UInt8) -> Bool {
        (byte >= 97 && byte <= 122) || (byte >= 48 && byte <= 57) || byte == 35 || byte == 43
    }
    while index < bytes.count {
        guard isWordStart(bytes[index]) else {
            index += 1
            continue
        }
        let start = index
        index += 1
        while index < bytes.count, isWordBody(bytes[index]) {
            index += 1
        }
        let token = String(decoding: bytes[start..<index], as: UTF8.self)
        if token.utf8.count < 4 || timelineTopicStopwords.contains(token) || seen.contains(token) {
            continue
        }
        seen.insert(token)
        tokens.append(token)
    }
    return tokens
}

// MARK: - groupTimelineSections

/// Port of `groupTimelineSections`: `date` buckets by day, `type` by entry
/// kind, `topic` by the most-shared significant keyword — entries sharing no
/// repeated keyword land in "Everything else" (last). Section order follows
/// first appearance in the (already newest-first) input.
public func groupTimelineSections(
    _ entries: [TimelineEntry],
    _ grouping: TimelineGrouping,
    nowMs: Int64 = 0,
    calendar: Calendar = Calendar.current
) -> [TimelineSection] {
    if entries.isEmpty { return [] }

    if grouping == .topic {
        var frequency: [String: Int] = [:]
        var entryTokensById: [String: [String]] = [:]
        for entry in entries {
            let tokens = topicTokens(entry)
            entryTokensById[entry.id] = tokens
            for token in tokens {
                frequency[token, default: 0] += 1
            }
        }
        func topicOf(_ entry: TimelineEntry) -> String {
            let tokens = entryTokensById[entry.id] ?? []
            var best: String?
            var bestCount = 1
            for token in tokens {
                let count = frequency[token] ?? 0
                if count > bestCount {
                    best = token
                    bestCount = count
                }
            }
            guard let best else { return otherTopicLabel }
            // First letter uppercased, rest untouched (JS charAt/slice port).
            let first = best.prefix(1).uppercased()
            return first + best.dropFirst()
        }

        var sections: [TimelineSection] = []
        var other: [TimelineEntry] = []
        for entry in entries {
            let label = topicOf(entry)
            if label == otherTopicLabel {
                other.append(entry)
                continue
            }
            if let index = sections.firstIndex(where: { $0.label == label }) {
                sections[index].entries.append(entry)
            } else {
                sections.append(
                    TimelineSection(key: "topic-\(label)", label: label, entries: [entry])
                )
            }
        }
        if !other.isEmpty {
            sections.append(
                TimelineSection(key: "topic-other", label: otherTopicLabel, entries: other)
            )
        }
        return sections
    }

    var sections: [TimelineSection] = []
    for entry in entries {
        let label: String
        switch grouping {
        case .type:
            label = entry.kind.label
        case .date:
            label = timelineDayLabel(atMs: entry.atMs, nowMs: nowMs, calendar: calendar)
        case .topic:
            label = otherTopicLabel  // unreachable; kept for exhaustiveness
        }
        if let index = sections.firstIndex(where: { $0.label == label }) {
            sections[index].entries.append(entry)
        } else {
            sections.append(
                TimelineSection(key: "\(grouping.rawValue)-\(label)", label: label, entries: [entry])
            )
        }
    }
    return sections
}
