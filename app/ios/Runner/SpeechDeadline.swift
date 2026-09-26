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
