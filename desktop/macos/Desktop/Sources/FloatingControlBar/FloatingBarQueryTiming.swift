import Foundation

/// Per-query timing telemetry for the floating bar's "Ask Omi" + PTT paths.
///
/// One `FloatingBarQueryTiming` is created when the user fires a query and lives
/// until the response finishes (or is cancelled). Marked stages are appended in
/// order; `final` is set exactly once via `endQuery(...)`.
///
/// This is a pure value type. Side effects (writing the log file, emitting
/// PostHog events) live in `FloatingBarTimingLogger`. The split keeps the
/// arithmetic testable without touching the file system or analytics SDKs.
///
/// Stages are NOT hardcoded to the judge's benchmark prompts. They cover the
/// generic pipeline so any query — visible, hidden, casual, agent — is measured
/// the same way.
public struct FloatingBarQueryTiming: Codable, Equatable, Sendable {
    /// Stable identifier for the query (UUID). Lets us correlate log entries
    /// with PostHog events and with any debug breadcrumbs.
    public let queryId: String

    /// Wall-clock start (the moment the user fired the query — typing submit
    /// or PTT key release with non-empty transcript). Used as t=0 for all
    /// `msSinceStart` values.
    public let startedAt: Date

    /// How the query was triggered.
    public let source: Source

    /// Length of the user-supplied text (typed or transcribed). Does not
    /// include any context the system prompt injects.
    public let queryLength: Int

    /// Model used for the query. May be nil if the query was cancelled
    /// before `provider.sendMessage` resolved a model. Mutable so the call
    /// site can fill it in after the model is resolved (right before the
    /// provider's `sendMessage` is called).
    public var model: String?

    /// Append-only timeline of stage marks, ordered by call order.
    public private(set) var stages: [StageMark] = []

    /// Populated exactly once by `endQuery(...)`. Nil until then.
    public private(set) var final: Final?

    public init(
        queryId: String = UUID().uuidString,
        startedAt: Date = Date(),
        source: Source,
        queryLength: Int,
        model: String? = nil
    ) {
        self.queryId = queryId
        self.startedAt = startedAt
        self.source = source
        self.queryLength = queryLength
        self.model = model
    }

    // MARK: - Nested types

    public enum Source: String, Codable, Sendable {
        case text
        case voice
        case notification  // future: notification -> chat
    }

    /// Named pipeline stages. Adding a new stage is non-breaking — older log
    /// readers ignore unknown stages.
    public enum Stage: String, Codable, CaseIterable, Sendable {
        /// t=0. The moment the user fired the query.
        case userInput

        /// Router (Haiku) classification completed. For a hidden query that
        /// bypasses the router, this stage is marked immediately after
        /// `userInput` with the fast-path note in the `note` field.
        case routerDone

        /// Quota check (local or network) completed. Allows query to proceed.
        case quotaDone

        /// Screenshot capture (and downscale + WebP encode) completed. For
        /// non-visual queries that skip the capture, this stage is marked
        /// with `note: "skipped"` so totals stay comparable.
        case screenshotDone

        /// First text delta arrived from the AI provider. This is the
        /// "user-perceived time to first token" stage.
        case firstDelta

        /// The full response has been streamed (isStreaming flipped to false).
        /// Not always observed — if the query is cancelled mid-stream, the
        /// collector emits `endQuery` with `cancelled: true` instead.
        case complete
    }

    public struct StageMark: Codable, Equatable, Sendable {
        public let stage: Stage
        /// Milliseconds elapsed since `startedAt`, computed at the moment of
        /// the mark. Double, not Int, so sub-millisecond tests can use it.
        public let msSinceStart: Double
        /// Optional free-form note (e.g. "skipped", "fast_path", "bypass").
        public let note: String?
        /// Wall-clock time the stage was marked. Useful for correlating with
        /// other log lines (e.g. router HTTP request timestamps).
        public let wallClock: Date

        public init(stage: Stage, msSinceStart: Double, wallClock: Date, note: String? = nil) {
            self.stage = stage
            self.msSinceStart = msSinceStart
            self.wallClock = wallClock
            self.note = note
        }
    }

    public struct Final: Codable, Equatable, Sendable {
        public let totalMs: Double
        public let hadScreenshot: Bool
        public let toolCallCount: Int
        public let promptTokens: Int?
        public let completionTokens: Int?
        public let costUsd: Double?
        public let cancelled: Bool
        public let reason: EndReason
        public let error: String?

        public init(
            totalMs: Double,
            hadScreenshot: Bool,
            toolCallCount: Int,
            promptTokens: Int? = nil,
            completionTokens: Int? = nil,
            costUsd: Double? = nil,
            cancelled: Bool = false,
            reason: EndReason = .completed,
            error: String? = nil
        ) {
            self.totalMs = totalMs
            self.hadScreenshot = hadScreenshot
            self.toolCallCount = toolCallCount
            self.promptTokens = promptTokens
            self.completionTokens = completionTokens
            self.costUsd = costUsd
            self.cancelled = cancelled
            self.reason = reason
            self.error = error
        }
    }

    public enum EndReason: String, Codable, Sendable {
        /// Streaming completed naturally.
        case completed
        /// User stopped the response (Escape, PTT release cancel, etc.).
        case stopped
        /// Routed to a background agent pill — no inline chat response.
        case routedToAgent
        /// Quota exceeded (free user out of messages).
        case quotaExceeded
        /// Bridge / provider error.
        case error
    }

    // MARK: - Mutating API

    /// Record a stage mark. Idempotent per stage — re-marking the same stage
    /// keeps only the FIRST mark (the first mark is the one users perceive).
    /// Different stages can be marked in any order so the collector stays
    /// flexible as the pipeline evolves.
    public mutating func mark(_ stage: Stage, now: Date = Date(), note: String? = nil) {
        if stages.contains(where: { $0.stage == stage }) {
            return  // first mark wins
        }
        let ms = now.timeIntervalSince(startedAt) * 1000.0
        stages.append(StageMark(stage: stage, msSinceStart: ms, wallClock: now, note: note))
    }

    /// Populate `final` and mark `.complete` if not already marked.
    /// `now` defaults to the current wall clock and `totalMs` is computed from
    /// `startedAt` unless explicitly overridden (tests override to remove
    /// timing flake).
    public mutating func endQuery(
        now: Date = Date(),
        hadScreenshot: Bool,
        toolCallCount: Int,
        promptTokens: Int? = nil,
        completionTokens: Int? = nil,
        costUsd: Double? = nil,
        cancelled: Bool = false,
        reason: EndReason = .completed,
        error: String? = nil
    ) {
        let totalMs = now.timeIntervalSince(startedAt) * 1000.0
        final = Final(
            totalMs: totalMs,
            hadScreenshot: hadScreenshot,
            toolCallCount: toolCallCount,
            promptTokens: promptTokens,
            completionTokens: completionTokens,
            costUsd: costUsd,
            cancelled: cancelled,
            reason: reason,
            error: error
        )
        // Always mark .complete on endQuery so the timeline is contiguous
        // even for cancelled/quota-exceeded paths. Use the supplied `now` so
        // the .complete mark and `final.totalMs` agree.
        if !stages.contains(where: { $0.stage == .complete }) {
            let ms = now.timeIntervalSince(startedAt) * 1000.0
            stages.append(StageMark(
                stage: .complete,
                msSinceStart: ms,
                wallClock: now,
                note: cancelled ? "cancelled" : nil
            ))
        }
    }

    // MARK: - Read helpers

    /// ms for a given stage, or nil if not marked.
    public func ms(for stage: Stage) -> Double? {
        stages.first(where: { $0.stage == stage })?.msSinceStart
    }

    /// ms between two stages. Returns nil if either is missing.
    /// Useful for the per-stage deltas in dashboards ("router added 320ms").
    public func deltaMs(from: Stage, to: Stage) -> Double? {
        guard let fromMs = ms(for: from), let toMs = ms(for: to) else { return nil }
        return toMs - fromMs
    }
}
