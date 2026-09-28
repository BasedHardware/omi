import Foundation

// Port of the data layer of `react-native/src/desktop/timeline/UnifiedTimeline.tsx`
// and the filter/grouping vocabulary of `react-native/src/desktop/desktopChrome.ts`.
// Pure Foundation: no UI, deterministic (timestamps and "now" are injected).

// MARK: - Filter and grouping vocabulary (desktopChrome.ts)

/// `desktopActivityFilters` — All / Conversations / Recall / Tasks.
public enum TimelineFilter: String, Sendable, Hashable, CaseIterable {
    case all
    case conversations
    case recall
    case tasks

    /// Port of `desktopFilterLabel`.
    public var label: String {
        switch self {
        case .all: return "All"
        case .conversations: return "Conversations"
        case .recall: return "Recall"
        case .tasks: return "Tasks"
        }
    }
}

/// `desktopTimelineGroupings` — Date / Type / Topic.
public enum TimelineGrouping: String, Sendable, Hashable, CaseIterable {
    case date
    case type
    case topic

    public var label: String {
        switch self {
        case .date: return "Date"
        case .type: return "Type"
        case .topic: return "Topic"
        }
    }
}

// MARK: - Entry model

public enum TimelineEntryKind: String, Sendable, Hashable {
    case conversation
    case memory
    case task
    case capture

    /// `kindMeta[…].label` from UnifiedTimeline.tsx.
    public var label: String {
        switch self {
        case .conversation: return "Conversation"
        case .memory: return "Memory"
        case .task: return "Task"
        case .capture: return "Recall"
        }
    }
}

public struct TimelineEntry: Sendable, Hashable, Identifiable {
    public var id: String
    public var kind: TimelineEntryKind
    public var atMs: Int64
    public var title: String
    public var detail: String

    public init(id: String, kind: TimelineEntryKind, atMs: Int64, title: String, detail: String) {
        self.id = id
        self.kind = kind
        self.atMs = atMs
        self.title = title
        self.detail = detail
    }
}

/// Local capture group summary as rendered in the timeline. The groups
/// themselves are produced natively (600 s same-app+window dedupe in
/// `apple/OmiRewindCapture.mm`); this is the input shape only.
public struct CaptureGroupSummary: Sendable, Hashable {
    public var id: String
    public var title: String
    public var appName: String
    public var capturedAtMs: Int64
    public var count: Int

    public init(id: String, title: String, appName: String, capturedAtMs: Int64, count: Int) {
        self.id = id
        self.title = title
        self.appName = appName
        self.capturedAtMs = capturedAtMs
        self.count = count
    }
}

// MARK: - Read outcomes
// `ReadOutcome` / `DesktopReadOutcomes` are defined once in
// `Backend/DesktopReadClient.swift`; the timeline merges whatever loaded.

// MARK: - Entry construction

/// `secondsOrMillisToMs` — projections mix second and millisecond epochs;
/// normalize to milliseconds.
func secondsOrMillisToMs(_ value: Int64) -> Int64 {
    return value > 1_000_000_000_000 ? value : value * 1000
}

private func fallbackTitle(_ raw: String, _ fallback: String) -> String {
    return raw.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines).isEmpty ? fallback : raw
}

func conversationEntry(_ item: ConversationProjection) -> TimelineEntry {
    let iso = item.finishedAt ?? item.startedAt ?? item.createdAt
    let atMs = parseEpochMilliseconds(iso) ?? 0
    return TimelineEntry(
        id: "conversation-\(item.id)", kind: .conversation, atMs: atMs,
        title: fallbackTitle(item.title, "Conversation"), detail: item.summary
    )
}

func memoryEntry(_ item: MemoryProjection) -> TimelineEntry {
    let atMs = item.timestamp.map { secondsOrMillisToMs($0) } ?? 0
    return TimelineEntry(
        id: "memory-\(item.id)", kind: .memory, atMs: atMs,
        title: fallbackTitle(item.title, "Memory"), detail: item.summary
    )
}

func taskEntry(_ item: TaskProjection) -> TimelineEntry {
    let stamp = item.completedAt ?? item.dueAt
    let detail: String
    if item.completed, item.completedAt != nil {
        detail = "Done · \(item.summary)"
    } else {
        detail = item.summary
    }
    return TimelineEntry(
        id: "task-\(item.id)", kind: .task, atMs: stamp.map { secondsOrMillisToMs($0) } ?? 0,
        title: fallbackTitle(item.title, "Task"), detail: detail
    )
}

func captureEntry(_ item: CaptureGroupSummary) -> TimelineEntry {
    let detail = item.count > 1 ? "\(item.appName) · \(item.count) captures" : item.appName
    return TimelineEntry(
        id: "capture-\(item.id)", kind: .capture, atMs: item.capturedAtMs,
        title: item.title, detail: detail
    )
}

/// `entryFilterBucket` — captures land under Recall, tasks under Tasks,
/// everything else under Conversations.
func entryFilterBucket(_ kind: TimelineEntryKind) -> TimelineFilter {
    switch kind {
    case .capture: return .recall
    case .task: return .tasks
    default: return .conversations
    }
}

func matchesQuery(_ entry: TimelineEntry, _ query: String) -> Bool {
    let needle = query.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines).lowercased()
    if needle.isEmpty { return true }
    return "\(entry.title)\n\(entry.detail)".lowercased().contains(needle)
}

// MARK: - mergeTimeline

public struct MergedTimeline: Sendable, Hashable {
    public var entries: [TimelineEntry]
    public var failures: [String]

    public init(entries: [TimelineEntry], failures: [String]) {
        self.entries = entries
        self.failures = failures
    }
}

/// Port of `mergeTimeline` from UnifiedTimeline.tsx: merges conversation /
/// memory / task projections with local capture groups into one feed, newest
/// first (stable for equal timestamps), filtered and query-matched.
public func mergeTimeline(
    _ outcomes: DesktopReadOutcomes?,
    query: String = "",
    captures: [CaptureGroupSummary] = [],
    filter: TimelineFilter = .all
) -> MergedTimeline {
    guard let outcomes else { return MergedTimeline(entries: [], failures: []) }
    var failures: [String] = []
    var entries: [TimelineEntry] = []

    switch outcomes.conversations {
    case .success(let read): entries.append(contentsOf: read.items.map(conversationEntry))
    case .error: failures.append("Conversations are unavailable.")
    }
    switch outcomes.memories {
    case .success(let read): entries.append(contentsOf: read.items.map(memoryEntry))
    case .error: failures.append("Memories are unavailable.")
    }
    switch outcomes.tasks {
    case .success(let read): entries.append(contentsOf: read.items.map(taskEntry))
    case .error: failures.append("Tasks are unavailable.")
    }
    for item in captures {
        entries.append(captureEntry(item))
    }

    // Stable newest-first sort (Swift's sort is not documented stable; index
    // tiebreak matches the stable JS sort the TS relied on).
    let indexed = entries.enumerated().sorted { left, right in
        if left.element.atMs != right.element.atMs {
            return left.element.atMs > right.element.atMs
        }
        return left.offset < right.offset
    }
    let sorted = indexed.map(\.element)
    let filtered = sorted.filter { entry in
        (filter == .all || entryFilterBucket(entry.kind) == filter) && matchesQuery(entry, query)
    }
    return MergedTimeline(entries: filtered, failures: failures)
}
