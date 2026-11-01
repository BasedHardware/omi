import Foundation

/// A deadline for speech work whose underlying task may ignore cancellation
/// (notably a waiter on a shared model download). Completion has one owner;
/// timeout cleanup finishes before the caller may start another recognition.
@available(iOS 16.0, macOS 13.0, *)
@MainActor
final class SpeechDeadline<Value> {
    private var completion: ((Value) -> Void)?
    private var operationTask: Task<Void, Never>?
    private var timerTask: Task<Void, Never>?
    private let onTimeout: () async -> Value

    private init(onTimeout: @escaping () async -> Value, completion: @escaping (Value) -> Void) {
        self.onTimeout = onTimeout
        self.completion = completion
    }

    static func run(
        seconds: Double,
        operation: @escaping () async -> Value,
        onTimeout: @escaping () async -> Value
    ) async -> Value {
        await withCheckedContinuation { continuation in
            let deadline = SpeechDeadline(onTimeout: onTimeout, completion: { continuation.resume(returning: $0) })
            deadline.operationTask = Task {
                let value = await operation()
                deadline.finish(value)
            }
            deadline.timerTask = Task {
                do {
                    try await Task.sleep(for: .seconds(seconds))
                } catch {
                    return
                }
                await deadline.expire()
            }
        }
    }

    private func finish(_ value: Value) {
        guard let complete = completion else { return }
        completion = nil
        timerTask?.cancel()
        timerTask = nil
        operationTask = nil
        complete(value)
    }

    private func expire() async {
        guard let complete = completion else { return }
        // Claim completion before awaiting cleanup. A late recognition callback
        // must not return success while cancellation is still in progress.
        completion = nil
        operationTask?.cancel()
        operationTask = nil
        timerTask = nil
        complete(await onTimeout())
    }
}

/// Shared by the real channel and hermetic native tests. A fallback is only
/// selected after its own permission/availability check, never assumed ready.
@MainActor
struct LocalSpeechReadiness {
    let engine: String
    let status: String
    var ready: Bool { status == "ready" }
    var wire: [String: String] { ["engine": engine, "status": status] }
}

@MainActor
struct LocalSpeechUnavailable: Error {
    let readiness: LocalSpeechReadiness
    var cause: NSError? = nil

    var wire: [String: Any] {
        var details: [String: Any] = readiness.wire
        if let cause {
            details["nativeErrorDomain"] = cause.domain
            details["nativeErrorCode"] = cause.code
        }
        return details
    }
}

@MainActor
struct SpeechFallbackCoordinator {
    let analyzerReady: () async -> Bool
    let legacyReady: () async -> LocalSpeechReadiness
    let analyze: () async throws -> String
    let legacy: () async throws -> String

    func readiness(preferAnalyzer: Bool) async -> LocalSpeechReadiness {
        if preferAnalyzer, await analyzerReady() {
            return LocalSpeechReadiness(engine: "speech_analyzer", status: "ready")
        }
        return await legacyReady()
    }

    func transcribe(preferAnalyzer: Bool) async throws -> String {
        if preferAnalyzer, await analyzerReady() {
            do { return try await analyze() } catch { /* Check the fallback before using it. */ }
        }
        let readiness = await legacyReady()
        guard readiness.ready else { throw LocalSpeechUnavailable(readiness: readiness) }
        do {
            return try await legacy()
        } catch let error as LocalSpeechUnavailable {
            throw error
        } catch {
            // Assets, permissions or Dictation can change after the probe.
            // Recheck the actual recognizer before treating this as transient;
            // never infer missing assets from a localized error message.
            let current = await legacyReady()
            guard current.ready else {
                throw LocalSpeechUnavailable(readiness: current, cause: error as NSError)
            }
            throw error
        }
    }
}
