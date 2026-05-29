import Foundation
import os

// MARK: - QueryInputMode

enum QueryInputMode: String, Codable, Sendable {
    case text
    case voicePTTBatch = "voice_ptt_batch"
    case voicePTTLive = "voice_ptt_live"
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
    let finish_reason: String?
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

        // Include tool call details from nested spans
        let toolCalls = spans.flatMap { $0.children ?? [] }.filter { $0.name.hasPrefix("tool_call:") }
        if !toolCalls.isEmpty {
            let toolStrs = toolCalls.map { "\($0.name.replacingOccurrences(of: "tool_call:", with: ""))=\($0.dur_ms)ms" }
            parts.append("tools: \(toolStrs.joined(separator: ","))")
        }

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

private extension ContinuousClock.Instant.Duration {
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
        var finishReason: String?
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

    func span<T>(_ name: String, metadata: [String: String]? = nil, body: () throws -> T) rethrows -> T {
        begin(name, metadata: metadata)
        defer { end(name) }
        return try body()
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

    /// Capture the final response text + finish reason.
    func captureResponse(text: String, finishReason: String? = nil) {
        lock.withLock { state in
            state.responseText = text
            state.finishReason = finishReason
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
        // Copy raw state out of the lock, force-closing any orphaned spans
        let (completedSpans, ttftInstant, origin, traceId, query, inputMode,
             systemPrompt, messages, responseText, finishReason, hasScreenshot, toolExecutions) = lock.withLock { state in
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
            return (state.completedSpans, state.ttftInstant, state.origin, state.traceId, state.query, state.inputMode,
                    state.systemPrompt, state.messages, state.responseText, state.finishReason, state.hasScreenshot, state.toolExecutions)
        }

        // All conversion work happens outside the lock
        let now = ContinuousClock.now
        let totalMs = (now - origin).milliseconds
        let ttftMs: Int64? = ttftInstant.map { ($0 - origin).milliseconds }

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

        for (i, built) in completedSpans.enumerated() {
            let gapBefore: Int64?
            if i > 0 {
                let gap = built.start_ms - completedSpans[i - 1].end_ms
                gapBefore = gap
                if gap > Self.gapThresholdMs {
                    flaggedGaps.append(TraceFlaggedGap(
                        from: completedSpans[i - 1].name,
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
            system_prompt: systemPrompt,
            messages: messages,
            response_text: responseText,
            finish_reason: finishReason,
            has_screenshot: hasScreenshot
        )

        return QueryTrace(
            trace_id: traceId,
            timestamp: Self.isoFormatter.string(from: Date()),
            query_text: query,
            input_mode: inputMode.rawValue,
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
            tool_executions: toolExecutions.isEmpty ? nil : toolExecutions,
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

        // Dispatch JSON encoding + file I/O to a serial queue (no spinlock)
        Self.fileQueue.async {
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

        log(trace.summaryLine)
    }
}
