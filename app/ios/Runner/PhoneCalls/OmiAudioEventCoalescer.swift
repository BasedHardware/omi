import Foundation

/// Batches 20 ms Core Audio buffers into bounded events before they cross to Flutter.
///
/// The realtime callbacks deliver ~100 buffers/sec across two channels; posting each
/// one onto the Flutter EventChannel as its own Map (with a main-queue hop) is what a
/// CallKit-active call at 48 kHz cannot keep up with, so the stream silently dries up.
/// This coalescer appends buffers on a dedicated serial queue and emits one event per
/// channel once `flushBytes` (~100 ms) have accumulated. Pending audio is hard-capped:
/// beyond `maxPendingBytes` the oldest bytes are dropped so memory stays bounded and
/// the freshest audio keeps flowing.
final class OmiAudioEventCoalescer {
    private let queue: DispatchQueue
    private let flushBytes: Int
    private let maxPendingBytes: Int
    private let emit: (Data, Int) -> Void

    // Channel -> accumulated bytes; only touched on `queue`.
    private var pending: [Int: Data] = [:]
    private var droppedBytes = 0

    /// - Parameters:
    ///   - flushBytes: emit once a channel accumulates this many bytes.
    ///   - maxPendingBytes: per-channel cap; oldest bytes are dropped beyond it.
    ///   - emit: called on `queue` with one channel's coalesced payload.
    init(
        flushBytes: Int = 10_240,
        maxPendingBytes: Int = 40_960,
        label: String = "com.omi.phonecalls.audioevents",
        emit: @escaping (Data, Int) -> Void
    ) {
        self.queue = DispatchQueue(label: label)
        self.flushBytes = max(1, flushBytes)
        self.maxPendingBytes = max(self.flushBytes, maxPendingBytes)
        self.emit = emit
    }

    /// Called from the Core Audio realtime thread. Enqueues one immutable copy;
    /// no allocation beyond the Data boxes handed in by the device callbacks.
    func append(_ data: Data, channel: Int) {
        queue.async { [weak self] in
            guard let self = self else { return }
            var buffer = self.pending[channel] ?? Data()
            buffer.append(data)
            if buffer.count > self.maxPendingBytes {
                // Drop the oldest bytes down to one flush unit; count only the
                // drop so a saturated consumer is visible without dumping audio.
                self.droppedBytes += buffer.count - self.flushBytes
                buffer.removeFirst(buffer.count - self.flushBytes)
                if self.droppedBytes >= 102_400 {
                    print("OmiAudioEventCoalescer: dropped \(self.droppedBytes) bytes (channel \(channel))")
                    self.droppedBytes = 0
                }
            }
            if buffer.count >= self.flushBytes {
                self.pending[channel] = nil
                self.emit(buffer, channel)
            } else {
                self.pending[channel] = buffer
            }
        }
    }

    /// Drop any partial buffer (e.g. call teardown) without emitting.
    func reset() {
        queue.async { [weak self] in
            self?.pending.removeAll()
        }
    }
}
