import Foundation
import os

// MARK: - QueryInputMode

enum QueryInputMode: String, Codable, Sendable {
    case text
    case voicePTTBatch = "voice_ptt_batch"
    case voicePTTLive = "voice_ptt_live"
    case voicePTTOmni = "voice_ptt_omni"
}

// MARK: - Output Models

struct TraceSpan: Codable, Sendable {
    let name: String
    let start_ms: Int64
    let end_ms: Int64
    let dur_ms: Int64
    let gap_before_ms: Int64?
    let meta: [String: String]?
    let children: [TraceSpan]?

}

struct TraceFlaggedGap: Codable, Sendable {
    let from: String
    let to: String
    let gap_ms: Int64
}

struct TraceLLMRequest: Codable, Sendable {
    let system_prompt: String?
    let messages: [[String: String]]?
    let response_text: String?
    let has_screenshot: Bool
}

struct TraceToolExecution: Codable, Sendable {
    let tool_use_id: String?
    let name: String
    let input: String
    let output: String
    let dur_ms: Int64?
}

struct QueryTrace: Codable, Sendable {
    let trace_id: String
    let timestamp: String
    let query_text: String
    let input_mode: String
    let model: String?
    let total_ms: Int64
    let ttft_ms: Int64?
    let token_count: Int
    let tps: Double?
    let input_tokens: Int?
    let output_tokens: Int?
    let cache_read_tokens: Int?
    let cache_write_tokens: Int?
    let cost_usd: Double?
    let request: TraceLLMRequest?
    let tool_executions: [TraceToolExecution]?
    let spans: [TraceSpan]
    let flagged_gaps: [TraceFlaggedGap]

    enum CodingKeys: String, CodingKey {
        case trace_id, timestamp, query_text, input_mode, model
        case total_ms, ttft_ms, token_count, tps
        case input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd
        case request, tool_executions
        case spans, flagged_gaps
    }

    var summaryLine: String {
        var parts: [String] = ["[trace]"]
        parts.append("id=\(trace_id)")
        parts.append("mode=\(input_mode)")
        parts.append("total=\(total_ms)ms")
        if let ttft = ttft_ms {
            parts.append("ttft=\(ttft)ms")
        } else {
            parts.append("ttft=–")
        }
        if let tps = tps {
            parts.append("tps=\(String(format: "%.1f", tps))")
        }
        if let inp = input_tokens { parts.append("in=\(inp)") }
        if let out = output_tokens { parts.append("out=\(out)") }
        if let cr = cache_read_tokens, cr > 0 { parts.append("cache_read=\(cr)") }
        if let cw = cache_write_tokens, cw > 0 { parts.append("cache_write=\(cw)") }
        if let cost = cost_usd { parts.append("cost=$\(String(format: "%.4f", cost))") }
        let stages = spans.map { "\($0.name)=\($0.dur_ms)" }.joined(separator: "|")
        parts.append("stages: \(stages)")

        if flagged_gaps.isEmpty {
            parts.append("gaps: none")
        } else {
            let gapStrs = flagged_gaps.map { "[\($0.from)→\($0.to):\($0.gap_ms)ms]" }
            parts.append("gaps: \(gapStrs.joined(separator: " "))")
        }

        return parts.joined(separator: " ")
    }
}

// MARK: - TaskLocal Context

enum QueryTracerContext {
    @TaskLocal static var current: QueryTracer?
}

// MARK: - Duration Extension

extension ContinuousClock.Instant.Duration {
    var milliseconds: Int64 {
        let c = self.components
        return Int64(c.seconds) * 1000 + Int64(c.attoseconds) / 1_000_000_000_000_000
    }
}

// MARK: - QueryTracer

final class QueryTracer: @unchecked Sendable {

    static let gapThresholdMs: Int64 = 50
    private static let isoFormatter = ISO8601DateFormatter()

    private struct OpenSpan {
        let name: String
        var metadata: [String: String]?
        let startInstant: ContinuousClock.Instant
        var children: [BuiltSpan]
    }

    private struct BuiltSpan {
        let name: String
        let start_ms: Int64
        let end_ms: Int64
        let dur_ms: Int64
        let meta: [String: String]?
        let children: [BuiltSpan]?
    }

    private let lock: OSAllocatedUnfairLock<State>

    private struct State {
        var origin: ContinuousClock.Instant
        var query: String
        var inputMode: QueryInputMode
        var traceId: String
        var spanStack: [OpenSpan] = []
        var completedSpans: [BuiltSpan] = []
        var ttftInstant: ContinuousClock.Instant?

        // Full request/response capture
        var systemPrompt: String?
        var messages: [[String: String]]?
        var responseText: String?
        var hasScreenshot: Bool = false
        var toolExecutions: [TraceToolExecution] = []
    }

    init(query: String, inputMode: QueryInputMode) {
        let now = ContinuousClock.now
        let id = "t_" + (0..<6).map { _ in String(format: "%x", Int.random(in: 0...15)) }.joined()
        lock = OSAllocatedUnfairLock(initialState: State(
            origin: now,
            query: query,
            inputMode: inputMode,
            traceId: id
        ))
    }

    // MARK: - API

    func updateQuery(_ query: String) {
        lock.withLock { state in
            state.query = query
        }
    }

    func begin(_ name: String, metadata: [String: String]? = nil) {
        lock.withLock { state in
            state.spanStack.append(OpenSpan(
                name: name,
                metadata: metadata,
                startInstant: ContinuousClock.now,
                children: []
            ))
        }
    }

    func end(_ name: String, metadata: [String: String]? = nil) {
        lock.withLock { state in
            let endInstant = ContinuousClock.now
            // Search stack from top for matching name
            guard let idx = state.spanStack.lastIndex(where: { $0.name == name }) else { return }

            var span = state.spanStack.remove(at: idx)

            // Merge metadata
            if let meta = metadata {
                if span.metadata == nil {
                    span.metadata = meta
                } else {
                    for (k, v) in meta {
                        span.metadata?[k] = v
                    }
                }
            }

            let startMs = (span.startInstant - state.origin).milliseconds
            let endMs = (endInstant - state.origin).milliseconds
            let built = BuiltSpan(
                name: span.name,
                start_ms: startMs,
                end_ms: endMs,
                dur_ms: endMs - startMs,
                meta: span.metadata,
                children: span.children.isEmpty ? nil : span.children
            )

            if state.spanStack.isEmpty {
                state.completedSpans.append(built)
            } else {
                state.spanStack[state.spanStack.count - 1].children.append(built)
            }
        }
    }

    func span<T>(_ name: String, metadata: [String: String]? = nil, body: () async throws -> T) async rethrows -> T {
        begin(name, metadata: metadata)
        defer { end(name) }
        return try await body()
    }

    /// Record a zero-duration span that just marks a stage as skipped (with optional
    /// extra metadata). Collapses the `begin(…"skipped")`/`end` pair used at skip sites.
    func mark(_ name: String, metadata: [String: String] = [:]) {
        var meta = metadata
        meta["skipped"] = "true"
        begin(name, metadata: meta)
        end(name)
    }

    func markTTFT() {
        lock.withLock { state in
            guard state.ttftInstant == nil else { return }
            state.ttftInstant = ContinuousClock.now
        }
    }

    /// Capture the full system prompt + message history sent to the API.
    func captureRequest(
        systemPrompt: String,
        messages: [[String: String]],
        hasScreenshot: Bool = false
    ) {
        lock.withLock { state in
            state.systemPrompt = systemPrompt
            state.messages = messages
            state.hasScreenshot = hasScreenshot
        }
    }

    /// Capture the final response text.
    func captureResponse(text: String) {
        lock.withLock { state in
            state.responseText = text
        }
    }

    /// Capture a tool call execution (name, input, output, duration).
    func captureToolExecution(toolUseId: String?, name: String, input: String, output: String, durationMs: Int64? = nil) {
        lock.withLock { state in
            state.toolExecutions.append(TraceToolExecution(
                tool_use_id: toolUseId,
                name: name,
                input: input,
                output: output,
                dur_ms: durationMs
            ))
        }
    }

    func buildTrace(
        tokenCount: Int,
        model: String?,
        inputTokens: Int? = nil,
        outputTokens: Int? = nil,
        cacheReadTokens: Int? = nil,
        cacheWriteTokens: Int? = nil,
        costUsd: Double? = nil
    ) -> QueryTrace {
        // Snapshot the full state under the lock (State is all value types), force-closing
        // any orphaned spans first. Then release the heavy captured strings (system prompt,
        // message history, response, tool I/O) from the live tracer so a lingering reference
        // to it — e.g. the playback service holding `tracer` between queries — can't pin
        // them in memory after the trace is built. `snapshot` keeps what we still need.
        let snapshot: State = lock.withLock { state in
            // Drain unclosed spans so they're not silently lost
            let endInstant = ContinuousClock.now
            while let open = state.spanStack.popLast() {
                var meta = open.metadata ?? [:]
                meta["unclosed"] = "true"
                let startMs = (open.startInstant - state.origin).milliseconds
                let endMs = (endInstant - state.origin).milliseconds
                let built = BuiltSpan(
                    name: open.name,
                    start_ms: startMs,
                    end_ms: endMs,
                    dur_ms: endMs - startMs,
                    meta: meta,
                    children: open.children.isEmpty ? nil : open.children
                )
                if state.spanStack.isEmpty {
                    state.completedSpans.append(built)
                } else {
                    state.spanStack[state.spanStack.count - 1].children.append(built)
                }
            }
            let copy = state
            state.systemPrompt = nil
            state.messages = nil
            state.responseText = nil
            state.toolExecutions = []
            state.completedSpans = []
            return copy
        }

        // All conversion work happens outside the lock
        let now = ContinuousClock.now
        let totalMs = (now - snapshot.origin).milliseconds
        let ttftMs: Int64? = snapshot.ttftInstant.map { ($0 - snapshot.origin).milliseconds }

        let tps: Double?
        if let t = ttftMs, totalMs > t, tokenCount > 0 {
            let genMs = Double(totalMs - t)
            tps = genMs > 0 ? Double(tokenCount) / (genMs / 1000.0) : nil
        } else {
            tps = nil
        }

        // Convert BuiltSpan -> TraceSpan
        func convert(_ b: BuiltSpan, gapBefore: Int64?) -> TraceSpan {
            TraceSpan(
                name: b.name,
                start_ms: b.start_ms,
                end_ms: b.end_ms,
                dur_ms: b.dur_ms,
                gap_before_ms: gapBefore,
                meta: b.meta,
                children: b.children?.enumerated().map { (i, child) in
                    let childGap: Int64? = i > 0 ? child.start_ms - b.children![i-1].end_ms : nil
                    return convert(child, gapBefore: childGap)
                }
            )
        }

        var traceSpans: [TraceSpan] = []
        var flaggedGaps: [TraceFlaggedGap] = []

        for (i, built) in snapshot.completedSpans.enumerated() {
            let gapBefore: Int64?
            if i > 0 {
                let gap = built.start_ms - snapshot.completedSpans[i - 1].end_ms
                gapBefore = gap
                if gap > Self.gapThresholdMs {
                    flaggedGaps.append(TraceFlaggedGap(
                        from: snapshot.completedSpans[i - 1].name,
                        to: built.name,
                        gap_ms: gap
                    ))
                }
            } else {
                gapBefore = nil
            }
            traceSpans.append(convert(built, gapBefore: gapBefore))
        }

        let request = TraceLLMRequest(
            system_prompt: snapshot.systemPrompt,
            messages: snapshot.messages,
            response_text: snapshot.responseText,
            has_screenshot: snapshot.hasScreenshot
        )

        return QueryTrace(
            trace_id: snapshot.traceId,
            timestamp: Self.isoFormatter.string(from: Date()),
            query_text: snapshot.query,
            input_mode: snapshot.inputMode.rawValue,
            model: model,
            total_ms: totalMs,
            ttft_ms: ttftMs,
            token_count: tokenCount,
            tps: tps,
            input_tokens: inputTokens,
            output_tokens: outputTokens,
            cache_read_tokens: cacheReadTokens,
            cache_write_tokens: cacheWriteTokens,
            cost_usd: costUsd,
            request: request,
            tool_executions: snapshot.toolExecutions.isEmpty ? nil : snapshot.toolExecutions,
            spans: traceSpans,
            flagged_gaps: flaggedGaps
        )
    }

    // MARK: - File I/O

    private static let maxLogBytes: UInt64 = 5 * 1024 * 1024  // 5 MB
    private static let fileQueue = DispatchQueue(label: "com.omi.querytracer.file")

    private static let logDir: URL = {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/Omi")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }()

    func finalize(
        tokenCount: Int,
        model: String?,
        inputTokens: Int? = nil,
        outputTokens: Int? = nil,
        cacheReadTokens: Int? = nil,
        cacheWriteTokens: Int? = nil,
        costUsd: Double? = nil
    ) {
        let trace = buildTrace(
            tokenCount: tokenCount,
            model: model,
            inputTokens: inputTokens,
            outputTokens: outputTokens,
            cacheReadTokens: cacheReadTokens,
            cacheWriteTokens: cacheWriteTokens,
            costUsd: costUsd
        )

        // Dispatch summary logging + JSON encoding + file I/O to a serial queue
        // (no spinlock) so none of it runs on the @MainActor query path.
        Self.fileQueue.async {
            log(trace.summaryLine)

            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]

            guard let jsonData = try? encoder.encode(trace),
                  let jsonString = String(data: jsonData, encoding: .utf8)
            else { return }

            let logFile = Self.logDir.appendingPathComponent("traces.jsonl")

            // Rotate if over size limit
            if let attrs = try? FileManager.default.attributesOfItem(atPath: logFile.path),
               let size = attrs[.size] as? UInt64, size > Self.maxLogBytes {
                let backup = Self.logDir.appendingPathComponent("traces.1.jsonl")
                try? FileManager.default.removeItem(at: backup)
                try? FileManager.default.moveItem(at: logFile, to: backup)
            }

            if let handle = try? FileHandle(forWritingTo: logFile) {
                handle.seekToEndOfFile()
                if let lineData = (jsonString + "\n").data(using: .utf8) {
                    handle.write(lineData)
                }
                handle.closeFile()
            } else {
                // First write — create the file
                try? (jsonString + "\n").data(using: .utf8)?.write(to: logFile)
            }
        }
    }
}
