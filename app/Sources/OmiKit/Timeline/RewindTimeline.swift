import Foundation

// Port of `react-native/src/desktop/rewindTimeline.ts`: same-window frame
// grouping with the 12-minute gap bound, and the interleaved captured /
// shipping history reader. The bridge is injected, so everything stays
// deterministic and testable.

public struct RewindFrame: Sendable, Hashable {
    public var id: String
    public var capturedAtMs: Int64
    public var appName: String
    public var windowTitle: String

    public init(id: String, capturedAtMs: Int64, appName: String, windowTitle: String) {
        self.id = id
        self.capturedAtMs = capturedAtMs
        self.appName = appName
        self.windowTitle = windowTitle
    }
}

/// Consecutive frames over the same window collapse into one timeline moment.
/// The gap bound keeps a capture that paused (sleep, stop/start) from merging
/// into the previous session even though app and title match.
public struct RewindCaptureGroup: Sendable, Hashable {
    public var id: String
    public var frame: RewindFrame
    public var appName: String
    public var windowTitle: String
    public var capturedAtMs: Int64
    public var firstCapturedAtMs: Int64
    public var count: Int
}

let rewindGroupGapMs: Int64 = 12 * 60 * 1000

/// Port of `groupRewindFrames`: frames are expected newest-first; a frame
/// merges into the previous group when app and window title match and the
/// gap from the group's first (newest) frame is within 12 minutes.
public func groupRewindFrames(_ frames: [RewindFrame]) -> [RewindCaptureGroup] {
    var groups: [RewindCaptureGroup] = []
    for frame in frames {
        if var previous = groups.last,
            previous.appName == frame.appName,
            previous.windowTitle == frame.windowTitle,
            previous.firstCapturedAtMs - frame.capturedAtMs <= rewindGroupGapMs
        {
            previous.count += 1
            previous.firstCapturedAtMs = frame.capturedAtMs
            groups[groups.count - 1] = previous
            continue
        }
        groups.append(
            RewindCaptureGroup(
                id: frame.id, frame: frame, appName: frame.appName,
                windowTitle: frame.windowTitle, capturedAtMs: frame.capturedAtMs,
                firstCapturedAtMs: frame.capturedAtMs, count: 1
            )
        )
    }
    return groups
}

// MARK: - Interleaved rewind timeline

public enum RewindSourceKind: String, Sendable, Hashable, CaseIterable {
    case captured
    case shipping
}

public struct RewindFramePage: Sendable, Hashable {
    public var frames: [RewindFrame]
    public var nextCursor: String?

    public init(frames: [RewindFrame], nextCursor: String?) {
        self.frames = frames
        self.nextCursor = nextCursor
    }
}

public struct RewindTimelinePage: Sendable, Hashable {
    public var frames: [RewindFrame]
    public var next: Bool
    public var warning: String?

    public init(frames: [RewindFrame], next: Bool, warning: String? = nil) {
        self.frames = frames
        self.next = next
        self.warning = warning
    }
}

/// Failure codes the reader distinguishes, mirroring the TS `code` strings.
public enum RewindTimelineFailure: Error, Equatable, Sendable {
    /// `OMI_REWIND_AUTH` — retires the reader.
    case rewindAuth
    /// `OMI_REWIND_OWNER_CHANGED` — retires the reader.
    case ownerChanged
    /// `OMI_REWIND_UNAVAILABLE` — missing history is normal, no warning.
    case unavailable
    /// `OMI_REWIND_STORAGE` and other failures — warn once readable.
    case storage
}

public let rewindHistoryWarning = "Some screen history could not be loaded."

/// Bridge surface mirroring `RewindTimelineBridge.listFrames`.
/// Throwing `RewindTimelineFailure` carries the TS error codes; any other
/// thrown error is treated like `OMI_REWIND_STORAGE` (warn, keep readable).
public struct RewindTimelineBridge: Sendable {
    public var listFrames: @Sendable (
        _ source: RewindSourceKind, _ query: String, _ cursor: String?, _ limit: Int
    ) throws -> RewindFramePage

    public init(
        listFrames: @escaping @Sendable (
            _ source: RewindSourceKind, _ query: String, _ cursor: String?, _ limit: Int
        ) throws -> RewindFramePage
    ) {
        self.listFrames = listFrames
    }
}

private struct RewindSourceState {
    var kind: RewindSourceKind
    var frames: [RewindFrame] = []
    var cursor: String?
    var done = false
    var readable = false
}

/// Port of `createRewindTimeline`: interleaves the local captured store with
/// old Omi history, refilling both source heads before each pick. Equal
/// timestamps prefer `captured`; the `limit` of 50 matches the TS constant.
public final class RewindTimeline: @unchecked Sendable {
    private let bridge: RewindTimelineBridge
    private let query: String
    private let limit: Int
    private var sources: [RewindSourceState]
    private var failure: (any Error)?
    private var retired = false
    private var warning: String?

    public init(bridge: RewindTimelineBridge, query: String, limit: Int = 50) {
        self.bridge = bridge
        self.query = query
        self.limit = limit
        self.sources = RewindSourceKind.allCases.map { RewindSourceState(kind: $0) }
    }

    private func refill(_ source: inout RewindSourceState) throws {
        if !source.frames.isEmpty || source.done { return }
        do {
            let page = try bridge.listFrames(source.kind, query, source.cursor, limit)
            source.frames = page.frames
            source.cursor = page.nextCursor
            source.done = page.nextCursor == nil
            source.readable = true
        } catch {
            if let failure = error as? RewindTimelineFailure {
                switch failure {
                case .rewindAuth, .ownerChanged:
                    retired = true
                    self.failure = failure
                    throw failure
                case .unavailable:
                    source.done = true
                case .storage:
                    source.done = true
                    if !retired { self.failure = failure }
                    warning = rewindHistoryWarning
                }
            } else {
                source.done = true
                if !retired { self.failure = error }
                warning = rewindHistoryWarning
            }
        }
    }

    /// Port of `next()`. Synchronous: the bridge is a throwing closure.
    public func next() throws -> RewindTimelinePage {
        if retired { throw failure! }
        var frames: [RewindFrame] = []
        while frames.count < limit {
            // Refill both heads before choosing: a source's next page can
            // precede the other source's buffered frames.
            for index in sources.indices {
                try refill(&sources[index])
            }
            if retired { throw failure! }
            let available = sources.indices.filter { !sources[$0].frames.isEmpty }
            if available.isEmpty {
                if sources.contains(where: { !$0.done }) { continue }
                break
            }
            // Newest head wins; ties prefer the earlier source (captured).
            var newest = available[0]
            for candidate in available.dropFirst() {
                if sources[candidate].frames[0].capturedAtMs
                    > sources[newest].frames[0].capturedAtMs
                {
                    newest = candidate
                }
            }
            frames.append(sources[newest].frames.removeFirst())
        }
        if warning != nil, !sources.contains(where: { $0.readable }) {
            throw failure!
        }
        let next = sources.contains { !$0.frames.isEmpty || !$0.done }
        return RewindTimelinePage(
            frames: frames, next: next, warning: warning
        )
    }
}
