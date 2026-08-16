import Flutter
import Foundation

/// Monotonic capture epoch shared between the controller (writer) and the
/// event emitter (reader). Every tap closure bakes in the epoch it was
/// installed under; the emitter drops any frame whose epoch is no longer the
/// active one. This is what guarantees no frame is delivered after stop() and
/// none crosses a rebuild, without any locking on the tap path itself.
final class PhoneMicGeneration {
    private var lock = os_unfair_lock()
    private var counter: UInt64 = 0
    private var active: UInt64 = 0

    /// Starts a new capture epoch and returns it.
    func advance() -> UInt64 {
        os_unfair_lock_lock(&lock)
        defer { os_unfair_lock_unlock(&lock) }
        counter += 1
        active = counter
        return counter
    }

    /// Ends the current epoch: every in-flight frame becomes droppable.
    func invalidate() {
        os_unfair_lock_lock(&lock)
        defer { os_unfair_lock_unlock(&lock) }
        active = 0
    }

    func matches(_ epoch: UInt64) -> Bool {
        os_unfair_lock_lock(&lock)
        defer { os_unfair_lock_unlock(&lock) }
        return epoch != 0 && active == epoch
    }
}

/// The only object that touches PhoneMicFlutterApi. Serializes every outbound
/// call onto the main thread (Pigeon FlutterApi requirement) and epoch-gates
/// frames. Because frames and state events funnel FIFO through the main queue,
/// an epoch invalidation that happens-before a state emission means no frame
/// can arrive after that state event.
final class PhoneMicEventEmitter {
    private let api: PhoneMicFlutterApi
    private let generation: PhoneMicGeneration

    init(api: PhoneMicFlutterApi, generation: PhoneMicGeneration) {
        self.api = api
        self.generation = generation
    }

    func emitFrame(_ data: Data, epoch: UInt64, sessionId: Int64) {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.generation.matches(epoch) else { return }
            self.api.onAudioFrame(pcm16leMono16k: FlutterStandardTypedData(bytes: data), sessionId: sessionId) { _ in }
        }
    }

    func emitState(_ state: PhoneMicCaptureState, sessionId: Int64) {
        DispatchQueue.main.async { [weak self] in
            self?.api.onStateChanged(state: state, sessionId: sessionId) { _ in }
        }
    }

    func emitError(code: String, message: String, sessionId: Int64) {
        DispatchQueue.main.async { [weak self] in
            self?.api.onCaptureError(code: code, message: message, sessionId: sessionId) { _ in }
        }
    }

    /// Batch-mode 1Hz liveness/progress. Not epoch-gated: unlike frames it carries
    /// no audio, and its steady arrival is the Dart watchdog's liveness signal.
    func emitBatchProgress(_ capturedSeconds: Double, sessionId: Int64) {
        DispatchQueue.main.async { [weak self] in
            self?.api.onBatchProgress(capturedSeconds: capturedSeconds, sessionId: sessionId) { _ in }
        }
    }
}
